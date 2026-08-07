"""#498-r4-r1 -- GARDE de la FUITE de `UnitFlag.Undisplaceable` (0x19) hors de la charge de
`1152 UnstoppableMomentumReworked`.

`IdunBattleLogic.Entities.Abilities.Active.Loki.UnstoppableMomentumReworkedAbility$$ExecuteBehaviour`,
relu verbatim sur le build courant :

    Execute( AddFlag(Caster@0x48, 0x19) )
    cache = Cache( First( TilesBehindInLine(...), amount: this+0xf0 = 10 ), true )
    for (index = 0; index < this+0xf0; index++) {
        tile = SelectTile( AtIndex(cache, index) );
        if (tile == null) return;                      // <<< SORTIE SANS RemoveFlag
        if (!ExecuteBehaviourStep(...)) break;
    }
    Execute( RemoveFlag(Caster@0x48, 0x19) )

LA BOUCLE INDEXE, ELLE N'ITERE PAS. Des que la ligne est plus COURTE que 10 tuiles ET que la charge
la traverse INTEGRALEMENT, `SelectTile` rend `null` et le natif SORT SANS retirer le flag. Rien ne
vient le lever ensuite : `UnitFlagsComponent$$RemoveTurnFlags` ne retire que
`0, 1, 2, 3, 4, 0xc, 0x1b`, et le recensement EXHAUSTIF de #498-r4 (10 appelants de
`DSLBehaviors$$AddFlag`, 40 sites d'`UnitFlagsComponent$$Add`) etablit que cette ability est le SEUL
ecrivain de `0x19`. Le caster reste donc `Undisplaceable` POUR LE RESTE DE LA BATAILLE.

DEUX ECARTS, PAS UN. Le port portait un `try/finally` qui retirait TOUJOURS (degradation
PERMISSIVE) ; et `_set_charge_flag` abandonnait quand le `UnitFlagsComponent` etait absent, ce qui
est le cas de TOUTE unite sans aucun flag sur un etat recharge (`snapshot._load_unit_flags` ne
materialise le composant que sur une liste NON VIDE). Le second RENDAIT LE PREMIER INOBSERVABLE :
mesure live du 2026-08-07, le port ne posait meme pas le flag. Foyer du second : residu `#545`.

CONFRONTE LIVE : `probe_498r4r1_fuite_flag_undisplaceable_live.py` -- `orksNob` sur `MC1_67`, deux
bras. `fuite` (cible au coin, ligne d'UNE tuile) : natif `unitFlags = [1, 2, 3, 4, 25]` ; `retrait`
(BigTarget adjacent, charge stoppee) : `[1, 2, 3, 4]`. Le port d'avant perdait le flag sur le
premier.

ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        # PROPRE A CE FICHIER, pris LARGE : la charge traverse `abilities/loki/momentum.py`, les
        # feuilles DSL de mouvement, `runner/components.py` (`unit_extensions_is_displaceable`,
        # `UnitFlagsComponent`), les selecteurs de geometrie et le pathfinding.
        "scripts/python/engine/**/*.py",
        # LA CASCADE DES CONFTEST, mesuree (`probe_486r15`), pas devinee : tout fichier de
        # `tests/engine/` traine ces 16 modules racine par la seule cascade des conftest, sans en
        # toucher aucun (residu #531).
        "scripts/python/board.py", "scripts/python/catalog_inject.py",
        "scripts/python/engine_agreement_stages.py", "scripts/python/engine_validate.py",
        "scripts/python/hexgeo.py", "scripts/python/host_inputs.py",
        "scripts/python/rl_collect_batch.py", "scripts/python/stream_events.py",
        "scripts/python/symbols_layout.py", "scripts/python/unit_map.py",
        "scripts/python/probe_17_active_ability_used_gate.py",
        "scripts/python/probe_17_hammer_corpse.py",
        "scripts/python/probe_17_martial_inspiration.py",
        "scripts/python/probe_308_normal_attack_bonus.py",
        "scripts/python/probe_316_ability_prediction_target_traits.py",
        "scripts/python/probe_350r3b_triggered_average_forms.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE du CHEMIN DE SORTIE d'une boucle native et de l'etat qu'il laisse. "
              "Aucun RPC, aucun runner : la confrontation live vit dans "
              "`probe_498r4r1_fuite_flag_undisplaceable_live.py`.",
}

import pytest                                                               # noqa: E402

from engine.runner.abilities.loki import momentum as MOM                    # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent,    # noqa: E402
                                      StatsComponent, UnitComponent, UnitFlagsComponent,
                                      unit_extensions_is_displaceable)
from engine.runner.state import State                                       # noqa: E402
from engine.entities.unit_context import UnitContext                        # noqa: E402

FLAG = MOM.CHARGE_FLAG                     # `UnitFlag.Undisplaceable` = 0x19 = 25


def _board(cols=5, rows=5):
    """Le VRAI `Board` du moteur : grille pleine, marchable, elevation 0."""
    from engine.entities.pathfinding.board import Board
    tiles, n = [], 1
    for col in range(cols):
        for row in range(rows):
            tiles.append({"id": n, "col": col, "row": row, "walkable": True, "elevation": 0})
            n += 1
    return Board(tiles, adjacency="evenq")


def _etat(rows: int, caster_pos):
    """Un caster SEUL sur un plateau plat et vide. Aucune autre unite : la charge n'attaque rien,
    ne pousse rien, et chaque pas se reduit a `IsEmptyOrSteppable -> Move` -- donc chaque pas rend
    `true` et la boucle va jusqu'au bout de la ligne. C'est exactement le regime qui expose le
    CHEMIN DE SORTIE, sans qu'aucun autre etage n'y participe."""
    st = State()
    st.board = _board(rows=rows)
    e = st.add_entity(1)
    e.add_component(UnitComponent(visual_id="orksNob", alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    e.add_component(PositionComponent(col=caster_pos[0], row=caster_pos[1]))
    e.add_component(UnitFlagsComponent())
    # `ctx.traits` doit exister : le rail COMBAT (`collect_triggered_abilities`) le LIT sur chaque
    # entite au premier `entities_from_state`. Liste VIDE = aucune ability declenchee, donc rien
    # d'autre que le chemin de sortie n'entre dans la mesure.
    e.add_component(StatsComponent(ctx=UnitContext(entity_id=1, visual_id="orksNob", traits=[])))
    return st


def _charge(st, aim_xy):
    ab = MOM.UnstoppableMomentumReworkedAbility()
    aim = st.board.id_at(aim_xy[0], aim_xy[1])
    return ab.execute_behaviour(st, 1, aim)


def _a_le_flag(st, uid=1):
    fc = st.get_entity(uid).get_component(UnitFlagsComponent)
    return fc is not None and fc.has(FLAG)


# =================================================================================================
# ETAGE 1 -- LIGNE COURTE ENTIEREMENT TRAVERSEE : le `return` du (4), et le flag RESTE
# =================================================================================================

def test_ligne_COURTE_traversee_le_flag_FUIT():
    """`SelectTile(AtIndex(cache, index)) == null` -> `return` AVANT le `RemoveFlag`.

    Board 5x5, caster en (2,3), visee (2,2) : la ligne remonte la colonne jusqu'au bord, donc
    STRICTEMENT moins de 10 tuiles. Toutes libres -> tous les pas rendent `true` -> l'index sort du
    cache."""
    st = _etat(rows=5, caster_pos=(2, 3))
    out = _charge(st, (2, 2))
    assert 0 < len(out["line"]) < MOM.MAX_CHARGE_TILES, (
        "le montage doit produire une ligne COURTE et NON VIDE : %r" % (out["line"],))
    assert out["steps"] == len(out["line"]), (
        "la charge doit avoir traverse TOUTE la ligne (sinon la sortie est un `break`) : %r"
        % (out,))
    assert out["flag_leaked"] is True
    assert _a_le_flag(st), "le natif SORT sans retirer 0x19 -- le port doit le laisser pose"


# =================================================================================================
# ETAGE 2 -- LES CHEMINS QUI ATTEIGNENT LE `RemoveFlag`. Sans eux, « le port ne retire jamais »
#            passerait l'etage 1.
# =================================================================================================

def test_ligne_de_DIX_tuiles_le_flag_est_RETIRE():
    """`index` atteint `this+0xf0` : la boucle sort par sa CONDITION, pas par le `return`. Le
    `First(line, 10)` a tronque, donc `AtIndex` ne sort jamais du cache."""
    st = _etat(rows=14, caster_pos=(2, 12))
    out = _charge(st, (2, 11))
    assert len(out["line"]) == MOM.MAX_CHARGE_TILES, (
        "le montage doit SATURER la troncature `First(line, 10)` : %r" % (out["line"],))
    assert out["steps"] == MOM.MAX_CHARGE_TILES
    assert out["flag_leaked"] is False
    assert not _a_le_flag(st), "sortie par la CONDITION de boucle -> le `RemoveFlag` est joue"


def test_charge_INTERROMPUE_le_flag_est_RETIRE(monkeypatch):
    """L'autre sortie normale : un pas rend `false` -> `break` -> `RemoveFlag`.

    Le pas est substitue plutot que monte : un vrai bloqueur (BigTarget) traine l'attaque, les
    effets et la poussee, donc trois etages qui n'ont RIEN a voir avec le chemin de sortie. Le
    stub isole la seule variable qui nous interesse."""
    monkeypatch.setattr(MOM.UnstoppableMomentumReworkedAbility, "_execute_behaviour_step",
                        lambda self, *a, **k: False)
    st = _etat(rows=5, caster_pos=(2, 3))
    out = _charge(st, (2, 2))
    assert out["steps"] == 1, "le stub doit avoir ete atteint AU PREMIER pas : %r" % (out,)
    assert out["flag_leaked"] is False
    assert not _a_le_flag(st)


# =================================================================================================
# ETAGE 3 -- LE MUTANT : le `try/finally` d'AVANT. Il doit faire DISPARAITRE le seul ecart.
# =================================================================================================

def test_le_try_finally_d_avant_EFFACE_la_fuite(monkeypatch):
    """CONTRE-EPREUVE de l'etage 1. Le port d'avant retirait le flag sur TOUS les chemins de
    sortie ; reproduit ici en le RE-retirant apres coup, ce qui est strictement equivalent.

    `a_mordu` est evalue SEPAREMENT du verdict : on assertionne d'abord que la mutation a bien
    remplace le foyer (le `flag_leaked` du retour reste `True` -- c'est le CHEMIN qui n'a pas
    change, seul l'ETAT final change), puis que l'observable bascule."""
    cls = MOM.UnstoppableMomentumReworkedAbility
    orig = cls.execute_behaviour

    def patched(self, state, caster_id, target_id):
        try:
            return orig(self, state, caster_id, target_id)
        finally:
            MOM._set_charge_flag(state, caster_id, False)

    monkeypatch.setattr(cls, "execute_behaviour", patched)
    st = _etat(rows=5, caster_pos=(2, 3))
    out = _charge(st, (2, 2))
    assert out["flag_leaked"] is True, (
        "la mutation ne doit PAS changer le CHEMIN : si `flag_leaked` bascule, le mutant mesure "
        "autre chose que le retrait")
    assert not _a_le_flag(st), "sous le port d'avant, le flag DOIT etre perdu -- sinon le cliquet " \
                               "de l'etage 1 ne garde rien"


# =================================================================================================
# ETAGE 4 -- LE SUBSTRAT : `AddFlag` ne peut PAS etre un no-op silencieux
# =================================================================================================

def test_set_charge_flag_CREE_le_composant_absent():
    """`AddFlagBehaviour$$Execute` accede au `UnitFlagsComponent` et **LEVE** s'il est absent -- il
    ne l'ignore pas. Natif, le cas ne se produit jamais (`UnitFactory` monte le composant sur toute
    unite). Cote port, `snapshot._load_unit_flags` ne le materialise que sur une liste NON VIDE,
    donc une unite sans aucun flag n'en a pas.

    MESURE (probe live, bras `fuite`) : avec le `if fc is None: return` d'avant, le port ne posait
    RIEN -- l'ecart de fuite etait INOBSERVABLE, masque par un ecart de substrat en amont."""
    st = _etat(rows=5, caster_pos=(2, 3))
    e = st.get_entity(1)
    e.remove_component(UnitFlagsComponent)
    assert e.get_component(UnitFlagsComponent) is None, (
        "le montage doit reproduire l'etat d'une unite SANS `UnitFlagsComponent`")
    MOM._set_charge_flag(st, 1, True)
    assert _a_le_flag(st), "la pose doit MORDRE meme sans composant prealable"


def test_la_charge_pose_le_flag_meme_sans_composant_prealable():
    """Le meme fait, mais par le CHEMIN REEL (`execute_behaviour`) plutot que par le helper : c'est
    ce chemin-la que la mesure live a trouve muet."""
    st = _etat(rows=5, caster_pos=(2, 3))
    st.get_entity(1).remove_component(UnitFlagsComponent)
    _charge(st, (2, 2))
    assert _a_le_flag(st)


# =================================================================================================
# ETAGE 5 -- LE FLAG EST LU : sans lecteur, la fuite ne changerait aucun observable
# =================================================================================================

@pytest.mark.parametrize("pose,attendu", [(False, True), (True, False)])
def test_le_flag_pose_rend_le_caster_INDEPLACABLE(pose, attendu):
    """`IdunBattle.Entities.UnitExtensions$$IsDisplaceable` finit par
    `return !HasFlag(unit, 0x19) && !big`. Six lecteurs portes en dependent, dont la tete de
    `IdunBattle.Operations.DisplaceUnitOperation$$Execute` (tout push / pull / deplacement direct /
    echange de position) et `IdunBattle.Core.Services.DamagePrediction$$GetKnockback`.

    Les DEUX bras sont joues : un test qui n'exercerait que `pose=True` serait compatible avec un
    predicat constamment faux."""
    st = _etat(rows=5, caster_pos=(2, 3))
    if pose:
        MOM._set_charge_flag(st, 1, True)
    assert unit_extensions_is_displaceable(st.get_entity(1)) is attendu
