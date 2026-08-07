"""#287-r14 -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` : le port ne connait plus
qu'UN regime de cible, parce qu'il RESOUT comme le natif.

CE QUE CES ETAGES GARDENT
-------------------------
  [1] LES QUATRE BRANCHES + LE SELF-CAST, une par une, sur un substrat controle. L'ordre est celui
      du decompile (`self-cast > TargetIsTile > TargetIsMachine > TargetIsActor > GetUnit`) et la
      branche MACHINE n'essaie PAS `GetUnit` d'abord -- seule la branche ACTOR enchaine les deux.

  [2] IDEMPOTENCE. C'est elle qui autorise les DEUX branchements du port (`AbilityHandler` au rang
      natif, ET la tete des `execute_behaviour` tile-target) : chaque branche est un projecteur.
      Sans elle, la double application deplacerait la cible une deuxieme fois.

  [3] MASQUE NON RE-LU (`TARGETING_OPTIONS is None`) -> `target_id` INCHANGE. Meme doctrine que le
      gate de cible : sans masque le port ne devine pas, il ne transforme pas.

  [4] SUBSTRAT DE TUILES ABSENT (`state.board is None`) -> `target_id` INCHANGE. Ce n'est pas « la
      cible n'a pas de tuile », c'est « le port n'a pas charge le boardGraph » -- et le rabattre
      sur le `null` de `GetMainTile` transforme une NON-MESURE en REFUS. Mesure : sans ce repli,
      `test_valkyrie_strike_migration_live` passait de « l'arbre DSL pose 1022 » a
      `execute_behaviour -> None`, un no-op complet.

  [5] CLIQUET DE REGISTRE, voie BEHAVIOUR : pour toute ability `TargetIsTile`, un cast dont la
      cible est l'UNITE et un cast dont la cible est SA TUILE doivent produire le MEME etat. C'est
      le critere de la tranche, et il est verifie sur le registre ENTIER -- une ability neuve qui
      oublie la resolution rougit ici.

  [6] CLIQUET DE REGISTRE, voie HANDLER (`AbilityHandler.visit_ActiveAbilityMessage`, le chemin
      REEL du moteur) : le meme invariant, pour TOUTES les abilities du registre.

  [7] TEMOIN NON NUL. Les etages [5]/[6] compareraient deux no-op sans s'en apercevoir : on exige
      qu'un nombre plancher d'abilities `TargetIsTile` MUTENT reellement l'etat, sans quoi
      l'accord ne prouve rien (« accord en regime DEGENERE = zero preuve »).

  [8] LE GESTE EST OBLIGATOIRE AU REGISTRE -- balayage STATIQUE : toute classe dont le masque porte
      `TargetIsTile` appelle `get_actual_target` en tete de son `execute_behaviour`. C'est le
      pendant exact de « entrer au registre SANS son masque de ciblage = regression silencieuse » :
      le defaut est PERMISSIF (l'ability opere sur l'unite la ou le natif opere sur la tuile), donc
      ni erreur ni crash -- seul un cliquet le voit.

  [9] UNE MoW N'EST PAS UNE `Unit`. Le natif la classe `Machine` (lu dans
      `IdunBattle.Entities.UnitExtensions$$GetMachine`, qui rend l'entite elle-meme sur ce type)
      alors que le port lui pose un `UnitComponent` pour la rendre exercable. Sans le discriminant
      `MachineComponent`, `GetUnit(<MoW>)` rendrait la MoW la ou le natif rend `null`.

 [10] LE PORTEUR DE `1022` EST LA TUILE (valeur MESUREE live, #287-r12, `MC1_67` seed 777 : le
      natif publie dans `tileMeta.tiles[].effects` et `decisionView.units[].effects` reste
      inchange). C'est l'etage qui ancre la tranche a une mesure, pas a une lecture.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre DECLARE LARGE sur `engine/**`, et c'est MESURE : les etages [5]/[6] chargent le
#: REGISTRE ENTIER d'abilities et jouent chacune, donc la fermeture d'imports traverse tout
#: `engine/**`. Hors de ce paquet, les chemins sont NOMMES UN PAR UN -- pas de
#: `scripts/python/*.py` fourre-tout, qui serait un `toujours: True` deguise (mesure #486-r24 :
#: 43 des 52 declencheurs du parc y cedent, et le cliquet ne rougit que sur le TROP ETROIT, donc
#: il RECOMPENSE la facilite).
#:
#: ⚠ Les 41 modules de RACINE ci-dessous ne sont PAS importes par ce fichier : ils viennent de la
#: cascade des `conftest` (celui de `tests/engine/runner/` importe des probes pour ses helpers).
#: Ils sont DERIVES, jamais devines --
#:     python -c "import probe_486r15_declencheurs_tests as P; \
#:                d,_=P.declarations(P.fichiers_de_test()); \
#:                print(P.confronter({<ce fichier>: d[<ce fichier>]})[0])"
#: rend la liste exacte. Si la cascade `conftest` change, ce declencheur ROUGIT -- et c'est le
#: comportement voulu : la fermeture de ce test a change, donc il doit se rejouer.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py",
        # importes DIRECTEMENT par ce fichier
        "scripts/python/probe_287r14_get_actual_target.py",
        "scripts/python/probe_287r12_role_target_tuile.py",
        "scripts/python/hexgeo.py",
        # tires par la cascade `conftest` (liste DERIVEE, cf. la commande ci-dessus)
        "scripts/python/board.py", "scripts/python/catalog_inject.py",
        "scripts/python/declencheur_guard.py", "scripts/python/engine_agreement_stages.py",
        "scripts/python/engine_validate.py", "scripts/python/enum_maps.py",
        "scripts/python/gameconfig.py", "scripts/python/green_skip_guard.py",
        "scripts/python/host_inputs.py", "scripts/python/probe_159_ah_bounds.py",
        "scripts/python/probe_178_overkill_gate.py",
        "scripts/python/probe_17_active_ability_used_gate.py",
        "scripts/python/probe_17_hammer_corpse.py",
        "scripts/python/probe_17_martial_inspiration.py",
        "scripts/python/probe_195_prevent_overkill_decision.py",
        "scripts/python/probe_207_haze_pool_ladder.py",
        "scripts/python/probe_207_haze_target_finder.py",
        "scripts/python/probe_220_haze_bonded_chain.py",
        "scripts/python/probe_270d_lysander_deploy.py",
        "scripts/python/probe_294_trigger_ability_channels.py",
        "scripts/python/probe_301_kill_unit_trigger_channels.py",
        "scripts/python/probe_306_effect_trigger_channels.py",
        "scripts/python/probe_308_normal_attack_bonus.py",
        "scripts/python/probe_316_ability_prediction_target_traits.py",
        "scripts/python/probe_334_defend_the_divine_work.py",
        "scripts/python/probe_338_ai_target_choice.py",
        "scripts/python/probe_348_ai_approach.py",
        "scripts/python/probe_350r3b_triggered_average_forms.py",
        "scripts/python/probe_357_relic_rail.py",
        "scripts/python/probe_363_ability_states_channel.py",
        "scripts/python/probe_487_hellfyre_missile_rack.py",
        "scripts/python/probe_dpw_weapon_cell.py", "scripts/python/probe_o5_unit_flags.py",
        "scripts/python/probe_psychic_aoe.py", "scripts/python/probe_r34_overkill_decision.py",
        "scripts/python/probe_r6_round_materialize.py", "scripts/python/probe_r6c_ah_bounds.py",
        "scripts/python/rl_collect_batch.py", "scripts/python/stream_events.py",
        "scripts/python/symbols_layout.py", "scripts/python/unit_map.py",
        # ⚠ HORS de `scripts/python/` -- donc aucun glob ci-dessus ne les couvre. La cascade
        # d'import du registre LIT ces deux entrees versionnees.
        "frida/hooks/data/ability-names.ts", "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le foyer `actual_target` est traverse par le chemin d'execution de TOUTE ability "
              "active (`AbilityHandler`) et par la tete des 23 `execute_behaviour` tile-target ; "
              "les etages de registre chargent `ABILITY_CLASSES` en entier.",
}

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_287r14_get_actual_target as P                                  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType           # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                 # noqa: E402
from engine.runner.abilities.targeting import TargetingOptions              # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR      # noqa: E402
from engine.runner.components import MachineComponent                       # noqa: E402
from probe_287r12_role_target_tuile import (POS_CIBLE, U_CASTER, U_CIBLE,   # noqa: E402
                                            _board, _tid)

VALKYRIE = int(ActiveAbilityType.ValkyrieStrike)          # 1018
VALK_EFFECT = 1022                                        # `Valkyrie_Strike_Effect`


def _foyer():
    """Import LOCAL des trois symboles NEUFS de la tranche (`actual_target`, `unit_id`,
    `machine_id`).

    ⚠ La raison n'est PAS un cycle : c'est que ce sont les SEULS symboles du fichier qui n'existent
    pas dans l'arbre d'AVANT. Au niveau module ils feraient echouer la COLLECTE sur l'arbre temoin,
    et un fichier non collecte ne montre AUCUN de ses autres etages -- la contre-epreuve rendrait
    `1 error` au lieu des rouges qui etablissent ce que la tranche repare. Meme parade que
    `test_287r12_role_target_tuile_offline` pour `main_tile_id`."""
    from engine.runner.abilities.behaviours import context
    return context.actual_target, context.unit_id, context.machine_id


def _tile_targets() -> list:
    """Les abilities du registre dont le masque porte `TargetIsTile` -- LU, jamais devine."""
    out = []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is not None and int(opts.rules) & int(TR.TargetIsTile):
            out.append((aid, cls))
    return out


@pytest.fixture(scope="module")
def board():
    return _board()


@pytest.fixture(scope="module")
def substrat(board):
    """Substrat commun aux etages unitaires : caster + cible au centre, board renseigne."""
    return P._montage_pour(VALKYRIE, board)


# ------------------------------------------------------------------ [1] les quatre branches

def test_etage1_les_quatre_branches_et_le_self_cast(substrat, board):
    """Mirror de `TargetingQuery$$GetActualTarget` -- chaque branche, dans l'ordre du decompile."""
    actual_target, _u, _m = _foyer()
    tuile = _tid(*POS_CIBLE)
    o_tile = TargetingOptions(rules=int(TR.TargetIsTile))
    o_unit = TargetingOptions(rules=int(TR.TargetIsEnemy))
    o_mach = TargetingOptions(rules=int(TR.TargetIsMachine))
    o_actr = TargetingOptions(rules=int(TR.TargetIsActor))
    o_self = TargetingOptions(rules=int(TR.TargetIsEnemy), self_cast=True)

    # TargetIsTile : l'UNITE comme sa TUILE rendent la TUILE -- c'est tout le sujet de la tranche.
    assert actual_target(substrat, o_tile, U_CASTER, U_CIBLE) == tuile
    assert actual_target(substrat, o_tile, U_CASTER, tuile) == tuile
    # branche par defaut `GetUnit` : l'unite rend l'unite, la tuile rend son OCCUPANT.
    assert actual_target(substrat, o_unit, U_CASTER, U_CIBLE) == U_CIBLE
    assert actual_target(substrat, o_unit, U_CASTER, tuile) == U_CIBLE
    # MACHINE : le natif n'essaie PAS `GetUnit` d'abord -> une UNITE ne resout PAS en machine.
    assert actual_target(substrat, o_mach, U_CASTER, U_CIBLE) is None
    # ACTOR : `GetUnit` d'abord, `GetMachine` en repli -> une unite passe.
    assert actual_target(substrat, o_actr, U_CASTER, U_CIBLE) == U_CIBLE
    # SELF-CAST : court-circuit en TETE, l'argument est ignore (y compris `None`).
    assert actual_target(substrat, o_self, U_CASTER, U_CIBLE) == U_CASTER
    assert actual_target(substrat, o_self, U_CASTER, None) == U_CASTER


def test_etage1b_la_branche_machine_ne_passe_pas_par_getunit(substrat):
    """Contre-epreuve de l'ordre : si le port enchainait `GetUnit` puis `GetMachine` sur le masque
    MACHINE (comme la branche ACTOR le fait), une cible UNITE resoudrait -- alors que le natif rend
    `null`. Les deux branches partagent leur repli, pas leur tete."""
    actual_target, _u, _m = _foyer()
    o_mach = TargetingOptions(rules=int(TR.TargetIsMachine))
    o_actr = TargetingOptions(rules=int(TR.TargetIsActor))
    assert actual_target(substrat, o_mach, U_CASTER, U_CIBLE) is None
    assert actual_target(substrat, o_actr, U_CASTER, U_CIBLE) is not None


# ------------------------------------------------------------------ [2] idempotence

def test_etage2_chaque_branche_est_un_projecteur(substrat):
    """Appliquer la resolution DEUX fois rend ce que la premiere a rendu. C'est ce qui autorise le
    double branchement (`AbilityHandler` + tete d'`execute_behaviour`)."""
    actual_target, _u, _m = _foyer()
    tuile = _tid(*POS_CIBLE)
    for opts in (TargetingOptions(rules=int(TR.TargetIsTile)),
                 TargetingOptions(rules=int(TR.TargetIsEnemy)),
                 TargetingOptions(rules=int(TR.TargetIsActor)),
                 TargetingOptions(rules=int(TR.TargetIsEnemy), self_cast=True)):
        for cible in (U_CIBLE, tuile, None):
            une = actual_target(substrat, opts, U_CASTER, cible)
            deux = actual_target(substrat, opts, U_CASTER, une)
            assert deux == une, f"non idempotent pour {opts.rules} sur {cible}: {une} -> {deux}"


# ------------------------------------------------------------------ [3]/[4] les deux non-mesures

def test_etage3_masque_non_relu_ne_transforme_rien(substrat):
    actual_target, _u, _m = _foyer()
    tuile = _tid(*POS_CIBLE)
    assert actual_target(substrat, None, U_CASTER, U_CIBLE) == U_CIBLE
    assert actual_target(substrat, None, U_CASTER, tuile) == tuile
    assert actual_target(substrat, None, U_CASTER, None) is None


def test_etage4_board_absent_ne_transforme_rien(substrat):
    """`state.board is None` = boardGraph NON CHARGE, pas « la cible n'a pas de tuile »."""
    actual_target, _u, _m = _foyer()
    board_reel = substrat.board
    try:
        substrat.board = None
        o_tile = TargetingOptions(rules=int(TR.TargetIsTile))
        assert actual_target(substrat, o_tile, U_CASTER, U_CIBLE) == U_CIBLE
    finally:
        substrat.board = board_reel
    # ... et avec le board, la meme entree resout bien en TUILE (temoin : le repli n'est pas
    # devenu la regle).
    assert actual_target(substrat, TargetingOptions(rules=int(TR.TargetIsTile)),
                         U_CASTER, U_CIBLE) == _tid(*POS_CIBLE)


# ------------------------------------------------------------------ [5]/[6]/[7] cliquets de registre

@pytest.fixture(scope="module")
def balayage_behaviour(board):
    return _balaye(board, "behaviour")


@pytest.fixture(scope="module")
def balayage_handler(board):
    return _balaye(board, "handler")


def _balaye(board, voie: str) -> dict:
    """Joue TOUT le registre dans les deux regimes et rend
    `{aid: (identiques, mute_l_etat, categorie)}`. Une ability qui LEVE sur ce montage generique
    est rangee a part -- jamais comptee comme conforme."""
    tuile = _tid(*POS_CIBLE)
    out, levees = {}, {}
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        cat = P._categorie(cls)
        try:
            u = P._joue(aid, cls, U_CIBLE, board, voie)
            t = P._joue(aid, cls, tuile, board, voie)
            vierge = P.empreinte_etat(P._montage_pour(aid, board))
        except Exception as exc:                                    # noqa: BLE001
            levees[aid] = type(exc).__name__
            continue
        out[aid] = (u == t, u[1] != vierge, cat)
    return {"resultats": out, "levees": levees}


def test_etage5_registre_voie_behaviour_les_tile_target_ne_connaissent_qu_un_regime(
        balayage_behaviour):
    """LE critere de la tranche, sur le registre ENTIER : `execute_behaviour(caster, <unite>)` et
    `execute_behaviour(caster, <sa tuile>)` produisent le MEME etat pour toute ability dont le
    masque porte `TargetIsTile`."""
    res = balayage_behaviour["resultats"]
    fautives = [aid for aid, (ident, _mute, cat) in res.items()
                if cat == "TargetIsTile" and not ident]
    assert not fautives, (
        "abilities TargetIsTile dont les deux regimes DIVERGENT (le port en connait deux la ou le "
        f"natif n'en a qu'un) : {fautives}")


def test_etage6_registre_voie_handler_aucune_ability_ne_diverge(balayage_handler):
    """Meme invariant sur le chemin REEL du moteur (`visit_ActiveAbilityMessage`, mirror
    d'`ActiveAbilityOperation$$ExecuteInternal`), et pour TOUTES les abilities -- pas seulement les
    tile-target : la resolution y est posee au rang natif, donc elle couvre aussi les branches
    machine / actor / self-cast."""
    res = balayage_handler["resultats"]
    fautives = [(aid, cat) for aid, (ident, _mute, cat) in res.items() if not ident]
    assert not fautives, f"abilities dont les deux regimes DIVERGENT par la voie handler: {fautives}"


def test_etage7_temoin_non_nul(balayage_behaviour, balayage_handler):
    """Un accord entre deux NO-OP ne prouve rien. On exige un plancher d'abilities `TargetIsTile`
    qui MUTENT reellement l'etat -- plancher MESURE a la tranche (21 voie behaviour, 8 voie
    handler, ou les gates de ciblage refusent la cible generique du montage), pris avec une marge
    pour ne pas rougir sur un montage qui derive."""
    for nom, bal, plancher in (("behaviour", balayage_behaviour, 15),
                               ("handler", balayage_handler, 6)):
        mutent = [aid for aid, (_i, mute, cat) in bal["resultats"].items()
                  if cat == "TargetIsTile" and mute]
        assert len(mutent) >= plancher, (
            f"voie {nom} : seulement {len(mutent)} ability(s) TargetIsTile mutent l'etat "
            f"(plancher {plancher}) -- l'accord des etages [5]/[6] serait DEGENERE")


# ------------------------------------------------------------------ [8] le geste au registre

def test_etage8_toute_ability_tile_target_resout_sa_cible_en_tete(balayage_behaviour):
    """Balayage STATIQUE du geste, pendant du « masque de ciblage pose DANS LE MEME COMMIT ».

    L'etage [5] est COMPORTEMENTAL : il reste vert pour une ability dont l'arbre ne lit pas le role
    `target` sur le montage generique. Celui-ci est STRUCTUREL -- il garde le geste lui-meme, donc
    il voit l'oubli AVANT qu'un substrat le revele."""
    import inspect
    manquantes = []
    for aid, cls in _tile_targets():
        lignes, _debut = inspect.getsourcelines(cls.execute_behaviour)
        if not any("get_actual_target" in ligne for ligne in lignes):
            manquantes.append((aid, cls.__name__))
    assert not manquantes, (
        "ability(s) TargetIsTile dont `execute_behaviour` n'appelle PAS `self.get_actual_target` : "
        f"{manquantes}. Le defaut est PERMISSIF (l'ability opere sur l'UNITE la ou le natif opere "
        "sur la TUILE) -- ni erreur ni crash.")


def test_etage8b_le_balayage_statique_a_de_quoi_mordre():
    """Le test ci-dessus rendrait VERT sur un ensemble VIDE. On assertionne son propre non-vide."""
    assert len(_tile_targets()) >= 20, (
        f"seulement {len(_tile_targets())} ability(s) TargetIsTile au registre -- le cliquet "
        "statique n'aurait presque rien a garder")


# ------------------------------------------------------------------ [9] MoW n'est pas une Unit

def test_etage9_une_mow_n_est_pas_une_unit(substrat):
    """`GetUnit` rend `null` sur une entite de type `Machine` ; `GetMachine` rend l'entite. Le port
    pose un `UnitComponent` sur la MoW (pour la rendre exercable), donc le discriminant est le
    `MachineComponent`."""
    actual_target, unit_id, machine_id = _foyer()
    e = substrat.get_entity(U_CIBLE)
    e.add_component(MachineComponent(slot=1))
    try:
        assert unit_id(substrat, U_CIBLE) is None
        assert machine_id(substrat, U_CIBLE) == U_CIBLE
        o_mach = TargetingOptions(rules=int(TR.TargetIsMachine))
        assert actual_target(substrat, o_mach, U_CASTER, U_CIBLE) == U_CIBLE
    finally:
        e.remove_component(MachineComponent)
    assert unit_id(substrat, U_CIBLE) == U_CIBLE
    assert machine_id(substrat, U_CIBLE) is None


# ------------------------------------------------------------------ [10] la mesure live ancree

def test_etage10_valkyrie_pose_1022_sur_la_tuile_dans_les_deux_regimes(board):
    """Mesure live #287-r12 (`MC1_67`, seed 777) : le natif inscrit `1022` dans
    `tileMeta.tiles[].effects` et `decisionView.units[].effects` reste INCHANGE. Le port doit donc
    poser sur la TUILE -- que l'appelant ait passe l'unite ou sa tuile."""
    tuile = _tid(*POS_CIBLE)
    porteurs = []
    for cible in (U_CIBLE, tuile):
        st = P._montage_pour(VALKYRIE, board)
        ABILITY_CLASSES[VALKYRIE]().execute_behaviour(st, U_CASTER, cible)
        porteurs.append(sorted(uid for uid, effs in st.effects.by_unit.items()
                               for e in effs if int(e.effect_type) == VALK_EFFECT))
    assert porteurs[0] == porteurs[1] == [tuile], (
        f"1022 doit etre porte par la TUILE {tuile} dans les DEUX regimes, mesure {porteurs}")


# ------------------------------------------------------------------ [11] le gate `finalTarget == null`

def test_etage11_le_gate_no_actual_target_est_ATTEIGNABLE(board):
    """`if (finalTarget == null) return 0;` -- le natif abandonne AVANT tout (ni behaviour, ni flag,
    ni vecteur d'operation). Ce gate n'est exerce par AUCUN des 258 casts du balayage generique
    (mesure), donc rien ne l'y garderait : ce sont ces branches-la qui derivent en silence. On
    l'exerce explicitement -- une ability UNIT-TARGET dont la cible est une TUILE VIDE :
    `UnitExtensions$$GetUnit(<tuile vide>)` rend `null` (le `TileContentComponent` n'est pas
    `IsFilled`), donc le cast doit etre un NO-OP COMPLET.

    ⚠ La contre-partie est l'etage [4] : quand c'est le SUBSTRAT qui manque (`board is None`), le
    port ne rabat PAS sur ce refus. Le gate ne mord que sur une resolution qui a REELLEMENT perdu
    une cible existante."""
    from engine.runner.abilities.handler import AbilityHandler
    from engine.runner.messages import ActiveAbilityMessage
    unit_target = next(((aid, cls) for aid, cls in sorted(ABILITY_CLASSES.items())
                        if P._categorie(cls) == "GetUnit (defaut)"), None)
    assert unit_target is not None, "aucune ability UNIT-TARGET au registre -- etage sans objet"
    aid, _cls = unit_target
    from engine.runner.components import PositionComponent
    st = P._montage_pour(aid, board)
    occupees = {st.board.id_at(pc.col, pc.row)
                for pc in (e.get_component(PositionComponent) for e in st.entities.values())
                if pc is not None}
    vide = next(t for t in sorted(st.board.by_id) if t not in occupees)
    h = AbilityHandler(st)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
        caster_id=U_CASTER, target_id=int(vide), ability_type=int(aid)))
    assert (h.last or {}).get("no_actual_target") is True, (
        f"ability {aid} sur la tuile VIDE {vide} : le gate `finalTarget == null` n'a pas mordu "
        f"(last={h.last})")
    assert P.empreinte_etat(st) == P.empreinte_etat(P._montage_pour(aid, board)), (
        "le gate a mordu mais l'etat a MUTE -- le natif abandonne AVANT la behaviour")


# ------------------------------------------------------------------ [12] le CADAVRE n'a plus de tuile

def test_etage12_un_cadavre_n_a_plus_de_tuile_donc_le_gate_cible_morte_mord_encore(board):
    """`IdunBattle.Entities.EntityExtensions$$GetMainTileId` cherche le composant de PIED, puis
    l'`OrderedSet` de pieds @+0x78 -- dont il sort par `return 0` quand il est VIDE. Le natif RETIRE
    du board l'unite tuee, donc `GetMainTile(<cadavre>)` rend `state.GetEntity(0)` = **null**.

    Cote port, `PositionComponent` SURVIT a la mort. Sans le filtre d'occupation dans `main_tile_id`,
    la resolution branchee EN AMONT du gate cible-morte (l'ordre natif) transformait
    `IsUnit(<cadavre>)` en `IsUnit(<tuile>)` = faux -> **le gate ne mordait plus** et le cast
    s'executait sur un cadavre. Regression PERMISSIVE, trouvee par
    `test_429r1r3_dead_target_message_gate_live` -- par le HARNAIS, pas par la lecture."""
    from engine.runner.components import HealthComponent, UnitComponent
    actual_target, _u, _m = _foyer()
    aid, cls = _tile_targets()[0]
    st = P._montage_pour(aid, board)
    mort = st.get_entity(U_CIBLE)
    mort.get_component(UnitComponent).alive = False
    mort.get_component(HealthComponent).hp = 0
    o_tile = TargetingOptions(rules=int(TR.TargetIsTile))
    assert actual_target(st, o_tile, U_CASTER, U_CIBLE) is None, (
        "un CADAVRE ne doit plus resoudre en tuile -- le natif rend `null`")
    # ... et la tuile elle-meme, passee directement, resout toujours (le filtre porte sur l'UNITE,
    # pas sur le board : sinon on aurait ferme le regime T avec).
    assert actual_target(st, o_tile, U_CASTER, _tid(*POS_CIBLE)) == _tid(*POS_CIBLE)
