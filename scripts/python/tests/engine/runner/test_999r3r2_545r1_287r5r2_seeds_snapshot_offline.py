"""#999-r3-r2 / #545-r1 / #287-r5-r2 -- GARDE des TROIS seeds de `runner/snapshot.py` livres par
cette tranche. MEME foyer, MEME forme : un champ que le CANAL publie (ou va publier) et que
`load_state` laissait tomber, donc un etat recharge repartait d'une valeur de construction.

Les trois etages qui MORDENT, et ce qu'ils rougissent sur l'arbre d'avant :

  A. RARETE des unites NON VIVANTES (`#999-r3-r2`). `BaseUnitComponent.Rarity` (+0x74) est lu par
     `IdunBattle.Entities.UnitExtensions$$HasRarity` et
     `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select`, sur une entite VIVANTE OU NON
     (le composant est la base commune de `UnitComponent` et `MachineComponent`). #999-r3 ne la
     branchait que sur `UnitContext`, bati depuis `combatSnapshot.units[]` -- un canal ALIVE-ONLY.
     Le canal la publie pourtant sur `unitsNotAlive[]` depuis #1039, pose EXACTEMENT pour la raison
     de #429-r1-r3-r1 (une unite qui a FUI garde sa rarete). MUTANT joue : `_load_unit_rarity`
     neutralisee = l'arbre d'avant, et l'etage doit RATER.

  B. `TotalAttacksMadeThisTurn` (`ActorStatisticsComponent+0x24`, ATTAQUES EMISES ce tour,
     `#545-r1`) et `NumAttacksReceivedThisTurn` (`+0x38`, RECUES, `#287-r5-r2`) : les deux
     compteurs PER-TOUR que `actorStats` ne publiait pas. Le TEMOIN de cet etage est le payload
     SANS les deux cles -- c'est-a-dire, litteralement, ce que le bundle d'avant rend -- et il doit
     laisser les compteurs a 0 (tri-etat : absent = non mesure, on ne touche a rien).

  C. Le CAPTEUR lui-meme, lu dans `frida/hooks/features/ai-step/rpc-snapshot.ts` : les deux champs
     y sont ECRITS. ⚠ Cet etage garde le CODE, pas le deploiement -- les deux champs n'arriveront
     dans un payload qu'apres une FENETRE DE REINJECT, qui appartient a l'orchestrateur.

ASCII only (cp1252).
"""
from __future__ import annotations

#: DECLENCHEUR -- ce qui doit changer pour que ce fichier puisse changer de verdict.
#: `engine/**` parce que l'etage A importe `load_state` (cascade large et MESUREE ailleurs) ;
#: la cascade `conftest` de ce repertoire pour la meme raison que ses voisins ; et le HOOK,
#: qu'aucun glob Python ne couvre alors que l'etage C le LIT.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
        "frida/hooks/features/ai-step/rpc-snapshot.ts",
        "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline : aucun runner, aucun RPC. Les etages A et B montent un `State` "
              "depuis des payloads SYNTHETIQUES et l'etage C lit un fichier source du depot. "
              "Aucune table de metadonnee du build n'est consultee -> `build: False`.",
}

import os                                                                # noqa: E402
import sys                                                               # noqa: E402
from pathlib import Path                                                 # noqa: E402

import pytest                                                            # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.entities.rarity import Rarity                                # noqa: E402
from engine.entities.selectors.units import UnitsWithRarity              # noqa: E402
from engine.runner import snapshot as SNAP                               # noqa: E402
from engine.runner.components import UnitComponent                       # noqa: E402
from engine.runner.abilities.behaviours.context import _unit_dict        # noqa: E402

#: `<racine>/scripts/python/tests/engine/runner/<ce fichier>` -> CINQ remontees.
RACINE = Path(__file__).resolve().parents[5]

COLS, ROWS = 5, 5
VIVANT, MORT = 10, 20
PLAYER_MOI, PLAYER_ADVERSE = 3, 4

#: Les DEUX raretes du montage, choisies DISTINCTES : un seed qui poserait une constante (ou qui
#: recopierait la rarete du vivant sur le mort) passerait un montage a valeur unique.
RARETE_VIVANT = Rarity.Epic          # 3
RARETE_MORT = Rarity.Mythic          # 5


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _payloads(rarete_mort=RARETE_MORT, canal_na="lu", rarity_enum="idun.meta.Rarity"):
    """`decisionView` + `observeBattle` + `combatSnapshot` d'un montage a DEUX unites, dont UNE
    MORTE -- exactement la topologie que le canal produit : le mort est GARDE par `decisionView`
    (cf. `project_decisionview_keeps_dead`) et ABSENT de `combatSnapshot.units[]`, qui est
    alive-only ; il n'existe que dans `unitsNotAlive[]`.

    `canal_na` reproduit les TROIS etats du canal, comme `_load_unit_flags` les nomme :
    `"lu"` (liste), `"muet"` (`null`), `"absent"` (champ absent -- bundle anterieur)."""
    decision = {"currentPlayer": PLAYER_MOI, "units": [
        {"id": VIVANT, "visualId": "bloodDeathCompany", "alive": True, "team": 1,
         "owner": PLAYER_MOI, "pos": {"col": 0, "row": 2}, "effects": []},
        {"id": MORT, "visualId": "necroWarden", "alive": False, "team": 2,
         "owner": PLAYER_ADVERSE, "pos": {"col": 4, "row": 4}, "effects": []},
    ]}
    observe = {"units": [{"squadId": VIVANT, "hp": 1000, "hpMax": 1000},
                         {"squadId": MORT, "hp": 0, "hpMax": 1000}]}
    snap = {"statTypes": {}, "rarityEnum": rarity_enum,
            "units": [{"entityId": VIVANT, "entityType": 1, "stats": {}, "unitFlags": [],
                       "rarity": int(RARETE_VIVANT)}]}
    if canal_na == "lu":
        snap["unitsNotAlive"] = [{"entityId": MORT, "entityType": 1, "unitFlags": [],
                                  "rarity": None if rarete_mort is None else int(rarete_mort)}]
    elif canal_na == "muet":
        snap["unitsNotAlive"] = None
    return decision, observe, snap


def _state(**kw):
    decision, observe, snap = _payloads(**kw)
    return SNAP.load_state(decision, observe, snapshot=snap,
                           board=Board(_tiles(), adjacency="evenq"))


# =================================================================================================
# ETAGE A -- LA RARETE D'UN MORT ENTRE DANS L'ETAT (#999-r3-r2)
# =================================================================================================

def test_a1_rarete_du_mort_seedee_depuis_units_not_alive():
    """Le mort n'a AUCUN `StatsComponent` (il n'est pas dans `units[]`) et porte pourtant sa
    rarete -- exactement ce que rend `GetBaseUnitComponent(e)-><+0x74>` sur une entite non
    vivante."""
    from engine.runner.components import StatsComponent
    st = _state()
    ent = st.get_entity(MORT)
    assert ent is not None, "le mort doit exister dans l'etat (decisionView le garde)"
    assert ent.get_component(StatsComponent) is None, (
        "PREMISSE du residu : aucun `UnitContext` n'est bati pour une ligne `unitsNotAlive` -- "
        "si ce n'est plus vrai, l'etage garde autre chose que ce qu'il croit")
    assert ent.get_component(UnitComponent).rarity == RARETE_MORT
    assert _unit_dict(st, MORT)["rarity"] == RARETE_MORT


def test_a2_le_vivant_est_inchange_et_les_deux_raretes_different():
    """Contre-epreuve d'ATTRIBUTION : le seed ne recopie pas une valeur unique. Le vivant garde la
    SIENNE (elle vient de son ctx, chemin d'origine #999-r3), le mort la sienne."""
    st = _state()
    assert _unit_dict(st, VIVANT)["rarity"] == RARETE_VIVANT
    assert _unit_dict(st, MORT)["rarity"] == RARETE_MORT
    assert int(RARETE_VIVANT) != int(RARETE_MORT), "montage DEGENERE : deux raretes egales"


def test_a3_le_selecteur_natif_retient_desormais_le_mort():
    """`UnitsWithRarity(<source>, Mythic)` = `IdunBattle.Entities.Formulas.UnitsWithRaritySelector
    $$Select` : `buc-><+0x74> == this-><+0x20>`. C'est le CONSOMMATEUR nomme par le residu -- la
    degradation etait qu'il rendait VIDE sur toute source de morts."""
    st = _state()

    class _Src:
        def __init__(self, ids):
            self.ids = ids

        def evaluate(self, ctx):
            return [_unit_dict(st, i) for i in self.ids]

    ret = UnitsWithRarity(_Src([VIVANT, MORT]), Rarity.Mythic).select(None)
    assert [u["id"] for u in ret] == [MORT]


def test_a4_mutant_seed_neutralise_fait_rater_l_etage(monkeypatch):
    """MUTATION ADVERSARIALE = l'arbre d'AVANT, a la ligne pres : `_load_unit_rarity` neutralisee.
    Le mort doit alors n'avoir AUCUNE rarete, et le selecteur redevenir VIDE.

    Substitution en FORME B (`SNAP.<nom>`) : le site d'appel de `load_state` lit l'attribut de
    module a chaque appel, donc le patch MORD (cf. la regle 'HISSER EN FORME B' du CLAUDE.md)."""
    monkeypatch.setattr(SNAP, "_load_unit_rarity", lambda state, snapshot: None)
    st = _state()
    assert st.get_entity(MORT).get_component(UnitComponent).rarity is None
    assert _unit_dict(st, MORT)["rarity"] is None

    class _Src:
        def evaluate(self, ctx):
            return [_unit_dict(st, MORT)]

    assert UnitsWithRarity(_Src(), Rarity.Mythic).select(None) == []


@pytest.mark.parametrize("canal", ["muet", "absent"])
def test_a5_canal_non_mesure_ne_pose_rien(canal):
    """TRI-ETAT : `unitsNotAlive` a `null` (capteur non resolu) ou ABSENT (bundle anterieur) laisse
    la rarete du mort a `None` -- comportement STRICTEMENT anterieur, jamais un `0` fabrique
    (`0` est `Rarity.Common`, une valeur plausible)."""
    st = _state(canal_na=canal)
    assert st.get_entity(MORT).get_component(UnitComponent).rarity is None
    assert st.unit_rarity_seed["units_not_alive"] is None, (
        "un canal non mesure doit rendre `None`, jamais `0` -- meme regle que `unit_flags_seed`")
    assert st.unit_rarity_seed["units_not_alive_channel"] == canal
    # Le VIVANT, lui, reste seede : le tri-etat porte sur le BLOC, pas sur la passe.
    assert _unit_dict(st, VIVANT)["rarity"] == RARETE_VIVANT


def test_a6_ligne_mesuree_sans_rarete_reste_non_mesuree():
    """`rarity: null` sur une ligne PRESENTE = mesure faite, valeur non lue (le resolveur du hook a
    refuse le canal). Meme issue que l'absence : on ne pose RIEN."""
    st = _state(rarete_mort=None)
    assert st.get_entity(MORT).get_component(UnitComponent).rarity is None
    assert st.unit_rarity_seed["units_not_alive"] == 0, (
        "canal LU mais aucune ligne porteuse -> `0`, qui est une MESURE (a distinguer du `None`)")


def test_a7_un_ordinal_hors_mirror_leve():
    """Un ordinal HORS de l'enum LEVE au lieu de se degrader en `None` : le seed passe par le foyer
    unique `entities.rarity.measured_rarity`, dont c'est le contrat. Un `None` silencieux ferait
    basculer tous les gates de rarete en RESTRICTIF sans que personne ne le voie."""
    decision, observe, snap = _payloads()
    snap["unitsNotAlive"][0]["rarity"] = 99
    with pytest.raises(ValueError):
        SNAP.load_state(decision, observe, snapshot=snap,
                        board=Board(_tiles(), adjacency="evenq"))


# =================================================================================================
# ETAGE B -- LES DEUX COMPTEURS PER-TOUR D'`ActorStatisticsComponent` (#545-r1, #287-r5-r2)
# =================================================================================================

#: Valeurs DISTINCTES et non triviales : un seed qui confondrait les deux champs (ou qui poserait
#: une constante) passerait un montage a valeur unique. Ni 0 ni 1.
EMISES, RECUES = 3, 7


def _actor_stats(**champs):
    """Un payload `actorStats` d'UNE ligne. Les cles NON passees sont ABSENTES -- c'est le TEMOIN
    exact du bundle d'avant cette tranche, qui ne les publiait pas."""
    return {"units": [dict({"entityId": VIVANT}, **champs)]}


def test_b1_les_deux_compteurs_sont_seedes():
    """`attacksMadeThisTurn` -> `UnitComponent.attacks_made_this_turn` (`+0x24`, lu par
    `components.unit_attacks_made_this_turn` = `IdunBattle.Entities.Formulas.
    AmountOfAttacksMadeThisTurnFormula$$Calculate`) ; `attacksReceivedThisTurn` ->
    `times_attacked_this_turn` (`+0x38`, lu par
    `IdunBattle.Entities.EntityExtensions$$GetNumAttacksReceivedThisTurn`)."""
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats(attacksMadeThisTurn=EMISES,
                                                 attacksReceivedThisTurn=RECUES))
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    assert uc.attacks_made_this_turn == EMISES
    assert uc.times_attacked_this_turn == RECUES


def test_b2_temoin_payload_sans_les_cles_ne_pose_rien():
    """LE TEMOIN, et c'est litteralement le bundle d'avant : les deux cles ABSENTES. Tri-etat ->
    les compteurs gardent leur `0` de construction. C'est ce qui rend le deploiement du capteur
    non bloquant pour le port."""
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats(totalAttacksMade=42))
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    assert (uc.attacks_made_this_turn, uc.times_attacked_this_turn) == (0, 0)
    assert uc.total_attacks_made == 42, "le champ DEJA publie doit rester seede (non-regression)"


def test_b3_valeur_negative_refusee():
    """GARDE `< 0` : les deux champs sont des compteurs a increments `>= 1`
    (`...$$RegisterAttackMade` / `...$$RegisterAttackReceived`) remis a `0` par leurs `Reset*`.
    Une valeur negative denonce une LECTURE invalide, jamais un etat de jeu -- meme signature que
    le `-1201836032` des tuiles (#340-r1)."""
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats(attacksMadeThisTurn=-1,
                                                 attacksReceivedThisTurn=-1))
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    assert (uc.attacks_made_this_turn, uc.times_attacked_this_turn) == (0, 0)


def test_b4_les_deux_champs_ne_sont_pas_confondus():
    """Contre-epreuve d'APPARIEMENT. `+0x24` (EMISES) et `+0x38` (RECUES) sont deux champs
    distincts aux lecteurs distincts, et `times_attacked_this_turn` n'est NI
    `total_times_attacked` (`+0x34`, cumul de BATAILLE) NI `turns_with_attacks_made` (`+0x30`, un
    compte de TOURS). Un echange serait SILENCIEUX si les deux valeurs etaient egales."""
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats(attacksMadeThisTurn=EMISES,
                                                 attacksReceivedThisTurn=RECUES,
                                                 totalTurnsWithAttacksMade=1,
                                                 totalAttacksMade=11))
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    assert EMISES != RECUES, "montage DEGENERE : un echange serait invisible"
    assert (uc.attacks_made_this_turn, uc.times_attacked_this_turn,
            uc.turns_with_attacks_made, uc.total_attacks_made,
            uc.total_times_attacked) == (EMISES, RECUES, 1, 11, 0)


# =================================================================================================
# ETAGE C -- LE CAPTEUR EST ECRIT (le DEPLOIEMENT, lui, attend une fenetre de reinject)
# =================================================================================================

HOOK = RACINE / "frida" / "hooks" / "features" / "ai-step" / "rpc-snapshot.ts"


@pytest.mark.parametrize("champ,nom_natif,repli", [
    ("attacksMadeThisTurn", "TotalAttacksMadeThisTurn", "0x24"),
    ("attacksReceivedThisTurn", "NumAttacksReceivedThisTurn", "0x38"),
])
def test_c_le_hook_publie_les_deux_champs(champ, nom_natif, repli):
    """Le champ est PUBLIE par le RPC `actorStats`, resolu PAR NOM avec repli DECOMPILE via
    `fieldOffsetOr` -- jamais `getFieldOffset(...) || <repli>`, qui ne prend JAMAIS le repli
    (`getFieldOffset` rend `-1`, *truthy* en JS ; c'est la faute mesuree de #340-r1).

    ⚠ Cet etage garde le CODE du capteur, pas son DEPLOIEMENT : les deux champs n'arriveront dans
    un payload qu'apres une fenetre de reinject."""
    src = HOOK.read_text(encoding="utf-8")
    assert 'fieldOffsetOr(asClass, "%s", %s)' % (nom_natif, repli) in src
    assert "%s: cp.add(" % champ in src
    assert 'getFieldOffset(asClass, "%s")' % nom_natif not in src
