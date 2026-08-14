"""#1079 -- le SEEDING de `NCContext` sur le chemin OFFLINE / face DECISION.

Trois canaux qui existaient DEJA en memoire et que le contexte de decision ne transportait pas.
Chaque etage MORD : la mutation qui retire le fil rougit, elle ne se contente pas de degrader.

  * etage 1-2 (#983-r1) -- le kit DECLENCHE d'ENTITE (`UnitContext.triggered_abilities`, seede par
    `snapshot._load_triggered_abilities`) n'arrivait pas a `AiDecisionContext.live_triggered_kits`
    hors LIVE : `rid == 0` rendait `{}` d'office.
  * etage 3-5 (#979-r1) -- la RAMPE `DutyEternalPlaybook$$GetUseProbability`, dont les DEUX
    extremites sont DETERMINISTES. Les bornes sont RE-LUES au decompile ici (l'enonce du residu
    les donnait DECALEES D'UN CRAN).
  * etage 6-8 (#1027-r5) -- les deux entrees de `BattleQuery$$HasMinimumRemainingTurns`. Les deux
    consommateurs lisaient `getattr(ctx, "state", None)`, un attribut que `NCContext` n'a JAMAIS
    porte : la valeur etait donc TOUJOURS `None`.

100 % OFFLINE (aucun runner, aucun RPC). ASCII only (console cp1252).
"""
from __future__ import annotations

from pathlib import Path

import pytest


#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Trop LARGE est sain ; trop ETROIT est un faux vert.
DECLENCHEUR = {
    "chemins": (
        # Les TROIS fils que ce fichier garde, de la source au consommateur.
        "scripts/python/engine/ai/context.py",           # `live_triggered_kits` + les 3 champs
        "scripts/python/engine/ai/state_bridge.py",      # les alimenteurs offline
        "scripts/python/engine/ai/action_generators.py",  # la propagation vers `NCContext`
        "scripts/python/engine/playbook/noncomparable/_base.py",       # les deux foyers
        "scripts/python/engine/playbook/noncomparable/duty_eternal.py",
        "scripts/python/engine/playbook/noncomparable/solar_atomizer.py",
        "scripts/python/engine/playbook/noncomparable/the_lantern.py",
        "scripts/python/engine/playbook/noncomparable/calibanite_greatsword.py",
        # Les foyers APPELES : une derive de leur corps deplace les verdicts d'ici.
        "scripts/python/engine/services/battle_query.py",
        "scripts/python/engine/services/victory_config.py",
        "scripts/python/engine/services/ability_caster_gates.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/victory_condition_type.py",
        # ENTREE versionnee qu'AUCUN import ne revele (`--proposer` le dit lui-meme : il ne voit
        # que les imports) -- c'est un `read_text`, et l'etage 6 en LIT la valeur.
        "data/seed-bc.json",
        # Le LECTEUR du gameconfig. Le gameconfig lui-meme vit HORS du depot
        # (`AppData/LocalLow/Snowprint/<produit>/gameconfig/<hash>.json`), donc AUCUN declencheur
        # de chemin ne peut voir qu'il a bouge -- c'est l'etage 3 qui le rend visible, en
        # assertionnant la valeur MESUREE au portage.
        "scripts/python/gameconfig.py",
    ),
    "build": False,   # aucune lecture du binaire ni de `data/symbols/**`
    "toujours": False,
    "raison": (
        "Ce fichier garde TROIS fils de seeding et rien d'autre : le kit DECLENCHE offline "
        "(#983-r1), la rampe `DutyEternalPlaybook$$GetUseProbability` (#979-r1) et les deux "
        "entrees de `BattleQuery$$HasMinimumRemainingTurns` (#1027-r5). Les modules cites sont "
        "la source, le transport et le consommateur de chacun -- `--proposer` les range dans la "
        "cascade DERIVEE, mais les declarer les rend LISIBLES au relecteur, et la cascade ne "
        "garantit pas qu'ils y restent. `data/seed-bc.json` est hors de toute fermeture "
        "d'imports (c'est un `read_text`) et l'etage 6 en LIT la valeur ; le gameconfig, lui, "
        "vit HORS DU DEPOT -- aucun declencheur ne peut le voir bouger, d'ou l'assertion de "
        "l'etage 3 sur `initialCooldownTurns = 2`. Pas de `build` : aucun etage ne "
        "touche le binaire ni `data/symbols/**` -- les VALEURS lues au decompile sont FIGEES "
        "dans le fichier (les bornes de la rampe, le slot 0x1b), et c'est `probe_313` qui garde "
        "les mirrors d'enum contre le build."
    ),
}


# =================================================================================================
# helpers de montage -- des doublures MINIMALES, jamais un runner
# =================================================================================================

class _Ctx:
    """Doublure de `UnitContext` : seul `triggered_abilities` compte ici (tri-etat)."""

    def __init__(self, triggered_abilities=None):
        self.triggered_abilities = triggered_abilities


class _Scene:
    """Doublure de `engine.playbook.Scene` -- `ctx_by_id` + les deux accesseurs de compteur."""

    def __init__(self, ctx_by_id=None, turns_finished_by_id=None):
        self.ctx_by_id = ctx_by_id or {}
        self._tf = turns_finished_by_id or {}

    def ctx(self, uid):
        return self.ctx_by_id.get(uid)

    def turns_finished(self, uid):
        return self._tf.get(uid)


class _Owner:
    def __init__(self, player):
        self.player = player


class _Entity:
    def __init__(self, player):
        self._owner = _Owner(player)

    def get_component(self, cls):
        from engine.runner.components import OwnerComponent
        return self._owner if cls is OwnerComponent else None


class _State:
    """Doublure de `State` : ce que lisent `get_player_turn_order` et
    `get_amount_of_turns_ended_by_player`, plus `victory_conditions`."""

    def __init__(self, players=(), turns_ended=None, victory_conditions=None):
        self.entities = {100 + i: _Entity(p) for i, p in enumerate(players)}
        self.turns_ended = turns_ended or {}
        self.victory_conditions = victory_conditions


def _lectures_getattr_state(src: str) -> list:
    """Les `getattr(<x>, "state", ...)` EXECUTABLES d'un source -- via l'AST, jamais par `in`.

    Un `in src` compterait aussi les occurrences en DOCSTRING et en COMMENTAIRE, or les deux
    fichiers concernes CITENT l'ancienne lecture pour expliquer la faute. Le vice est le meme que
    celui que `migrate_va_to_symbol.py` evite : ne reecrire (ici : ne compter) QUE le code."""
    import ast

    trouves = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "getattr" or len(node.args) < 2:
            continue
        arg = node.args[1]
        if isinstance(arg, ast.Constant) and arg.value == "state":
            trouves.append(node.lineno)
    return trouves


def _nc(**kw):
    from engine.playbook.noncomparable._base import NCContext

    base = dict(uid=7, origin=(0, 0), reach_nc=[], epos=[], fpos=[], plan={}, hp_cur_by_id={},
                units=[{"id": 7, "visualId": "ultraDreadnought"}])
    base.update(kw)
    return NCContext(**base)


# =================================================================================================
# ETAGE 1 (#983-r1) -- le pont offline PUBLIE ce qui est MESURE, et RIEN d'autre
# =================================================================================================

def test_etage1_le_pont_offline_ne_publie_QUE_les_entites_mesurees():
    """TRI-ETAT AU GRAIN DE L'ENTITE. Une unite dont `triggered_abilities is None` reste ABSENTE de
    la table -- surtout pas une liste vide, qui se lirait « cette unite ne porte aucun passif » et
    ferait RETIRER un id que le kit gameconfig connait (le sens exact de la faute #456-r1)."""
    from engine.ai.state_bridge import _triggered_kits_from_state

    scene = _Scene(ctx_by_id={
        7: _Ctx([1522, 1030]),      # MESUREE, porteuse
        8: _Ctx([]),                # MESUREE, et vide -- c'est une MESURE, elle doit sortir
        9: _Ctx(None),              # canal MUET -> jamais dans la table
    })
    table = _triggered_kits_from_state(scene)
    assert table == {7: [1522, 1030], 8: []}, table
    assert 9 not in table, "une entite NON MESUREE ne doit pas entrer dans la table"
    # Aucun substrat du tout -> table vide, pas une exception.
    assert _triggered_kits_from_state(None) == {}


def test_etage2_live_triggered_kits_SERT_le_pont_quand_rid_est_faux():
    """Le fil complet : `offline_triggered_kits` -> `live_triggered_kits()` -> le gate 1189.

    MUTATION QUI DOIT ROUGIR : rendre `{}` d'office quand `rid` est faux (le code d'avant) fait
    tomber la 2e assertion -- le gate ne voit plus l'id runtime et retombe sur le gameconfig."""
    from engine.ai.context import AiDecisionContext
    from engine.playbook.noncomparable.calibanite_greatsword import (
        CalibaniteGreatswordPlaybook, _EXCLUDING_TRIGGERED)

    def _mk(kits):
        return AiDecisionContext(
            rpc=lambda *a, **k: {}, rid=0, wt=None, predictor=None, sctx=None, scene=None,
            uid=7, me=None, units=[], cur=None, plans={}, enemies=[], epos=[], tgt_epos=[],
            fpos=[], origin=None, move_tiles=[], reach_nc=[], action_tiles=[], hp_cur_by_id={},
            hpmax_by_id={}, obs_units=[], ab_name_by_id={}, normal_ids=set(), elev_by_pos={},
            is_temporary_by_pos={}, effects_by_pos={}, pathdist_by_pos={}, tile_id_by_pos={},
            neigh_by_pos={}, walkable_by_pos={}, terrain_by_pos={}, offline_triggered_kits=kits)

    # Champ absent -> `{}` : le comportement d'AVANT, preserve mot pour mot.
    assert _mk(None).live_triggered_kits() == {}
    assert _mk(None).live_triggered_ability_ids(7) == []

    porteur = _mk({7: [int(_EXCLUDING_TRIGGERED)]})
    assert porteur.live_triggered_kits() == {7: [int(_EXCLUDING_TRIGGERED)]}
    assert porteur.live_triggered_ability_ids(7) == [int(_EXCLUDING_TRIGGERED)]
    assert porteur.live_triggered_ability_ids(8) == [], "unite non mesuree -> repli gameconfig"

    # Le CONSOMMATEUR voit desormais l'id runtime sur le chemin offline.
    p = CalibaniteGreatswordPlaybook()
    assert p._has_excluding_triggered_ability(
        _nc(units=[{"id": 7, "visualId": "darkaAzrael"}],
            triggered_kits=porteur.live_triggered_kits)) is True
    assert p._has_excluding_triggered_ability(
        _nc(units=[{"id": 7, "visualId": "darkaAzrael"}],
            triggered_kits=_mk(None).live_triggered_kits)) is False


# =================================================================================================
# ETAGE 3-5 (#979-r1) -- la RAMPE `DutyEternalPlaybook$$GetUseProbability`
# =================================================================================================

#: `constants.initialCooldownTurns` de `DutyEternal` sur ce build. FIGE ICI a la valeur MESUREE au
#: portage (cf. CLAUDE.md : `probe_313` compare le mirror au build et redevient vert apres une
#: regeneration, il ne garde PAS la valeur ecrite au site).
_DUTY_ETERNAL_INITIAL_COOLDOWN = 2


def test_etage3_la_constante_du_gameconfig_est_bien_celle_qui_a_ete_MESUREE():
    """`GetNumberConstant(0x68)` est `int.Parse(GetStringConstant(...))` : le natif ne degrade PAS.
    Si le gameconfig bouge, la rampe se decale de la meme quantite -- ce cran le rend visible."""
    import engine.services.ability_caster_gates as ACG
    from engine.entities.ability_constant_type import AbilityConstantType
    from engine.playbook.noncomparable.duty_eternal import DutyEternalPlaybook

    assert int(AbilityConstantType.initialCooldownTurns) == 0x68
    assert ACG.CONST_INITIAL_COOLDOWN == AbilityConstantType.initialCooldownTurns.name
    c = ACG.try_get_number_constant(DutyEternalPlaybook.ABILITY_ID, ACG.CONST_INITIAL_COOLDOWN)
    assert c == _DUTY_ETERNAL_INITIAL_COOLDOWN, (
        "initialCooldownTurns de DutyEternal a bouge (%r) -- la rampe se decale d'autant" % (c,))


def test_etage4_les_trois_branches_du_triage_de_probabilite():
    """`BasePlaybook$$ShouldEvaluate` : `>= 1` accepte, `<= 0` refuse, sinon TIRAGE (permissif).

    `None` = NON MESURE -> `True`, jamais un `0` invente : `Fix64.Zero` est la valeur qui fait
    REFUSER, donc un defaut prononcerait un refus que le natif n'a pas prononce."""
    from engine.playbook.noncomparable._base import probability_gate

    assert probability_gate(None) is True
    assert probability_gate(0.0) is False
    assert probability_gate(-0.99) is False
    assert probability_gate(1.0) is True
    assert probability_gate(1.32) is True
    assert probability_gate(0.33) is True and probability_gate(0.99) is True   # bande = permissif


def test_etage5_les_DEUX_extremites_de_la_rampe_MORDENT_aux_bornes_exactes():
    """`Fix64.FromIntFraction((t - c + 1) * 33, 100)`, avec `c = initialCooldownTurns`.

        (t - c + 1) * 33 <= 0    <=>  t <= c - 1   -> False DETERMINISTE
        (t - c + 1) * 33 >= 100  <=>  t >= c + 3   -> True  DETERMINISTE

    ⚠ LA BORNE HAUTE EST `>= c + 3`, PAS `>= c + 2` : `3 * 33 = 99 < 100`, et
    `FixMath.NET.Fix64$$FromIntFraction` divise en VIRGULE FIXE (`(long)(int)n << 0x20`), donc
    `99/100` vaut `0.99` et non `0`. L'enonce du residu donnait les deux bornes decalees d'un cran.

    MUTATION QUI DOIT ROUGIR : un `should_evaluate` qui rend `True` inconditionnellement (l'etat
    d'avant ce port) fait tomber les deux assertions `is False`."""
    from engine.playbook.noncomparable.duty_eternal import DutyEternalPlaybook

    p = DutyEternalPlaybook()
    c = _DUTY_ETERNAL_INITIAL_COOLDOWN

    def _ev(t):
        return p.should_evaluate(_nc(scene=_Scene(turns_finished_by_id={7: t})))

    def _prob(t):
        return p._use_probability(_nc(scene=_Scene(turns_finished_by_id={7: t})))

    # Extremite BASSE -- REFUS deterministe.
    for t in (0, c - 1):
        assert _prob(t) <= 0.0, t
        assert _ev(t) is False, "t=%d doit etre REFUSE (t <= c-1)" % t
    # Bande OUVERTE -- tirage natif, port PERMISSIF.
    for t, attendu in ((c, 0.33), (c + 1, 0.66), (c + 2, 0.99)):
        assert _prob(t) == pytest.approx(attendu, abs=1e-9), t
        assert 0.0 < _prob(t) < 1.0
        assert _ev(t) is True, "t=%d est dans la bande ALEATOIRE -> permissif assume" % t
    # Extremite HAUTE -- ACCEPTATION deterministe, et pas un cran plus tot.
    assert _prob(c + 3) == pytest.approx(1.32, abs=1e-9)
    assert _ev(c + 3) is True
    # Substrat absent -> NON MESURE -> permissif (jamais un refus fabrique).
    assert p._use_probability(_nc(scene=None)) is None
    assert p.should_evaluate(_nc(scene=None)) is True
    assert p._use_probability(_nc(scene=_Scene())) is None      # uid hors tables
    assert p.should_evaluate(_nc(scene=_Scene())) is True


# =================================================================================================
# ETAGE 6-8 (#1027-r5) -- `HasMinimumRemainingTurns` sur la face DECISION
# =================================================================================================

def test_etage6_le_gate_lit_le_plafond_TRANSPORTE_et_REFUSE_quand_il_mord():
    """`BattleQuery$$HasMinimumRemainingTurns(unit, 2)` : `turns <= limit - ended`.

    C'est une degradation PERMISSIVE qui se ferme : la ou un plafond EXISTE, le gate se met a
    REFUSER. C'est le correctif, pas une regression.

    MUTATION QUI DOIT ROUGIR : retirer `victory_conditions` du transport (le foyer retombe alors
    sur le defaut derive de la seed, ou la cle est ABSENTE) fait passer la 2e assertion a `True`."""
    from engine.entities.victory_condition_type import VictoryConditionType
    from engine.playbook.noncomparable._base import has_minimum_remaining_turns

    cle = VictoryConditionType.MainPlayerRoundLimitation.name

    # Canal NON FOURNI -> cascade du foyer -> defaut derive de la seed versionnee (pas de plafond).
    assert has_minimum_remaining_turns(_nc(), 2) is True
    # BC MESUREE et SANS plafond -> `Nullable` vide -> `true` sans rien lire d'autre (bras 1).
    assert has_minimum_remaining_turns(_nc(victory_conditions={}), 2) is True
    # BC MESUREE AVEC plafond, et il MORD : 2 <= 3 - 2 est FAUX.
    assert has_minimum_remaining_turns(
        _nc(victory_conditions={cle: 3}, turns_ended_by_first_player=2), 2) is False
    # Le meme plafond, plus tot dans la partie : 2 <= 3 - 0 est VRAI.
    assert has_minimum_remaining_turns(
        _nc(victory_conditions={cle: 3}, turns_ended_by_first_player=0), 2) is True
    # La borne EXACTE : 2 <= 3 - 1 est VRAI.
    assert has_minimum_remaining_turns(
        _nc(victory_conditions={cle: 3}, turns_ended_by_first_player=1), 2) is True


def test_etage7_les_deux_playbooks_ne_lisent_plus_un_attribut_INEXISTANT():
    """`getattr(ctx, "state", None)` valait TOUJOURS `None` -- `NCContext` n'a jamais eu ce champ.

    Deux crans : le champ n'existe toujours pas (donc rien ne l'a fait apparaitre par accident), et
    plus aucun des deux sites ne le lit."""
    import engine.playbook.noncomparable.solar_atomizer as SA
    import engine.playbook.noncomparable.the_lantern as TL
    from engine.playbook.noncomparable._base import NCContext

    assert "state" not in NCContext.__dataclass_fields__
    for mod in (SA, TL):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        # Le controle porte sur le CODE EXECUTABLE (AST), jamais sur le texte : la prose de ces
        # deux fichiers CITE l'ancienne lecture pour expliquer la faute, et un `in src` la
        # confondrait avec un appel -- un faux rouge sur le commentaire qui documente le fix.
        assert not _lectures_getattr_state(src), mod.__name__
        assert "NCB.has_minimum_remaining_turns(ctx, CASTER_MIN_REMAINING_TURNS)" in src
        assert mod.CASTER_MIN_REMAINING_TURNS == 2

    # Le gate ferme REELLEMENT le sweep des deux playbooks quand le plafond mord.
    from engine.entities.victory_condition_type import VictoryConditionType
    cle = VictoryConditionType.MainPlayerRoundLimitation.name
    ctx = _nc(victory_conditions={cle: 1}, turns_ended_by_first_player=0)
    assert SA.SolarAtomizerPlaybook().should_evaluate(ctx) is False
    assert TL.TheLanternPlaybook().should_evaluate(ctx) is False
    assert SA.SolarAtomizerPlaybook().generate_candidates(ctx) == []
    assert TL.TheLanternPlaybook().generate_candidates(ctx) == []


def test_etage8_le_bridge_offline_ALIMENTE_les_trois_champs():
    """Un champ de dataclass sans alimenteur est un mort-ne (le vice #943-r8). Les trois fils sont
    verifies de bout en bout : `state_bridge` les pose, `action_generators` les propage."""
    import engine.ai.action_generators as AG
    import engine.ai.state_bridge as SB
    from engine.ai.context import AiDecisionContext
    from engine.playbook.noncomparable._base import NCContext

    for champ in ("offline_triggered_kits", "victory_conditions", "turns_ended_by_first_player"):
        assert champ in AiDecisionContext.__dataclass_fields__, champ
    for champ in ("victory_conditions", "turns_ended_by_first_player"):
        assert champ in NCContext.__dataclass_fields__, champ

    src_sb = Path(SB.__file__).read_text(encoding="utf-8")
    assert "offline_triggered_kits=_triggered_kits_from_state(scene)" in src_sb
    assert 'victory_conditions=getattr(state, "victory_conditions", None)' in src_sb
    assert "turns_ended_by_first_player=_turns_ended_by_first_player(state)" in src_sb

    src_ag = Path(AG.__file__).read_text(encoding="utf-8")
    assert 'victory_conditions=getattr(ctx, "victory_conditions", None)' in src_ag
    assert 'turns_ended_by_first_player=getattr(ctx, "turns_ended_by_first_player", None)' in src_ag

    # `_turns_ended_by_first_player` DELEGUE aux deux foyers, et ne fabrique jamais un `0`.
    assert SB._turns_ended_by_first_player(None) is None
    st = _State(players=(5, 3), turns_ended={3: 4, 5: 9})
    assert SB._turns_ended_by_first_player(st) == 4, "le PREMIER du TurnOrder est le player 3"
    # Joueur present dans l'ordre mais absent du dictionnaire -> `0` par la branche `!ContainsKey`.
    assert SB._turns_ended_by_first_player(_State(players=(3,), turns_ended={})) == 0


# =================================================================================================
# ETAGE 9-10 (#1030-r2) -- l'empreinte 7-hex du caster A UNE POSITION DE MOUVEMENT
# =================================================================================================

def _grille(cols, rows):
    """Voisinage a 4 (suffisant : le port lit la LISTE STOCKEE, il ne la calcule pas) + elevation
    plate. C'est le substrat `boardGraph.neighbours` que `neigh_map` sert."""
    board = [(c, r) for c in range(cols) for r in range(rows)]
    neigh = {p: [q for q in board
                 if q != p and abs(q[0] - p[0]) + abs(q[1] - p[1]) == 1] for p in board}
    return board, neigh, {p: 0 for p in board}, {p: True for p in board}


def test_etage9_l_empreinte_est_RECONSTRUITE_a_chaque_position_pas_transportee():
    """`MovementQuery$$GetPossibleTileListsFromMovableTiles(movableTiles, numFeet)`, branche `7` :

        adj = <IBattleQuery slot 0x4f = GetAdjacentTiles>(t, 0, 1, 1)
        set = OrderedSet{ t }; set.AddRange(adj)

    donc `{t} U ring1(t)`, RECALCULE -- jamais une translation des offsets de l'origine. Le CENTRE
    est en TETE (`Add` avant `AddRange`) : `target_area` retranche `feet[:1]` = la MAIN TILE.

    MUTATION QUI DOIT ROUGIR : revenir a `return [position]` hors origine (l'etat d'avant) fait
    tomber la 3e assertion -- l'empreinte y retombe a une seule tuile."""
    from engine.playbook.noncomparable.the_lantern import TheLanternPlaybook, _CASTER_FEET_COUNT

    board, neigh, elev, walk = _grille(7, 7)
    origine = (3, 3)
    pieds = [origine] + neigh[origine]          # 1 + 4 sur cette grille de test
    obs = [{"id": 7, "visualId": "deathBossMortarion", "teamId": 1,
            "pos": {"col": c, "row": r}} for (c, r) in pieds]
    p = TheLanternPlaybook()

    # (a) substrat MONO-ligne -> le port n'INVENTE pas une empreinte : `[position]`.
    ctx1 = _nc(origin=origine, obs_units=[obs[0]], neigh_by_pos=neigh,
               elev_by_pos=elev, walkable_by_pos=walk)
    assert p._caster_footprint(ctx1, (5, 5)) == [(5, 5)]
    assert p._measured_feet(ctx1) == []

    # (b) substrat multi-ligne mais PAS 7 pieds -> hors de la branche native, aucune reconstruction.
    ctx2 = _nc(origin=origine, obs_units=obs, neigh_by_pos=neigh,
               elev_by_pos=elev, walkable_by_pos=walk)
    assert len(p._measured_feet(ctx2)) == 5 != _CASTER_FEET_COUNT
    assert p._caster_footprint(ctx2, (5, 5)) == [(5, 5)]

    # (c) SEPT pieds mesures -> l'empreinte est reconstruite A LA POSITION BALAYEE.
    sept = [origine] + neigh[origine] + [(1, 1), (1, 2)]     # 7 lignes mesurees
    obs7 = [{"id": 7, "visualId": "deathBossMortarion", "teamId": 1,
             "pos": {"col": c, "row": r}} for (c, r) in sept]
    ctx3 = _nc(origin=origine, obs_units=obs7, neigh_by_pos=neigh,
               elev_by_pos=elev, walkable_by_pos=walk)
    assert p._caster_footprint(ctx3, origine) == sept, "a l'origine, la MESURE fait autorite"
    emp = p._caster_footprint(ctx3, (5, 5))
    assert emp[0] == (5, 5), "le CENTRE est en TETE (`Add` avant `AddRange`)"
    assert set(emp[1:]) == set(neigh[(5, 5)]), emp
    assert len(emp) > 1, "hors origine, l'empreinte n'est plus mono-hex -- c'est le fix #1030-r2"


def test_etage10_le_ring1_de_l_empreinte_porte_les_filtres_LUS():
    """`GetAdjacentTiles(t, onlyEmptyOrSteppable: 0, onlyWalkableTiles: 1, allowTemporary: 1)` :
    porte d'elevation `|dElev| < 2` INCONDITIONNELLE + `IsWalkable` ARME. L'occupation, elle,
    n'est PAS filtree (`onlyEmptyOrSteppable = 0`)."""
    from engine.playbook.noncomparable.the_lantern import TheLanternPlaybook

    board, neigh, elev, walk = _grille(7, 7)
    origine = (3, 3)
    sept = [origine] + neigh[origine] + [(1, 1), (1, 2)]
    obs7 = [{"id": 7, "visualId": "deathBossMortarion", "teamId": 1,
             "pos": {"col": c, "row": r}} for (c, r) in sept]
    p = TheLanternPlaybook()
    cible = (5, 5)
    voisines = list(neigh[cible])

    # Une voisine NON MARCHABLE sort de l'empreinte.
    walk2 = dict(walk)
    walk2[voisines[0]] = False
    emp = p._caster_footprint(_nc(origin=origine, obs_units=obs7, neigh_by_pos=neigh,
                                  elev_by_pos=elev, walkable_by_pos=walk2), cible)
    assert voisines[0] not in emp and set(emp[1:]) == set(voisines[1:])

    # Une voisine a |dElev| >= 2 sort aussi -- porte INCONDITIONNELLE d'`IterateAdjacentTiles`.
    elev2 = dict(elev)
    elev2[voisines[1]] = 2
    emp = p._caster_footprint(_nc(origin=origine, obs_units=obs7, neigh_by_pos=neigh,
                                  elev_by_pos=elev2, walkable_by_pos=walk), cible)
    assert voisines[1] not in emp, "porte d'elevation |dElev| < 2 non appliquee"
    assert voisines[0] in emp, "les autres voisines restent"
