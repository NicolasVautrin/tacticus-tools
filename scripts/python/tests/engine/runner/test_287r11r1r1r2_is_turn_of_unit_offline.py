"""#287-r11-r1-r1-r2 -- GARDE du prefixe `IsTurnOfUnit` de `CasterHasNotMoved`, face RUNNER.

Le probe `probe_287r11r1r1r2_is_turn_of_unit.py` MESURE (live, `MC1_67`, 3 bras, ventilation
native `{0x0, 0x10}` non degeneree, 0 bras ecarte). Ce fichier GARDE ce que la mesure a etabli,
OFFLINE, et il est ecrit pour ROUGIR sur l'arbre d'avant la tranche :

  1. le SLOT et son ARITE, LUS dans `data/symbols/<build>/metadata/interface_slots.tsv` --
     `53 IsTurnOfUnit 1`, l'etage qui apparie le prefixe a son nom natif ;
  2. le mirror `runner.components.is_turn_of_unit` : ses CINQ issues, dont les trois `None` du
     tri-etat et le `False` du `if (GetUnit(unit) == null) return false` natif ;
  3. le CABLAGE dans `get_invalid_caster_reason` -- et la DIRECTION du tri-etat, qui est le
     livrable : seul un `False` MESURE saute la clause ; `None` la GARDE (sauter sur une
     non-mesure fabriquerait une acceptation) ;
  4. la BORNE : une ability qui ne pose PAS le bit ne consulte jamais le prefixe ;
  5. le GRAVAGE des trois bras de la mesure live, et le MUTANT (prefixe force a VRAI = l'etat de
     `master`), qui doit RATER le bras hors-tour -- le test assertionne son propre non-vide.

ASCII only (cp1252).
"""
from __future__ import annotations

#: DECLENCHEUR -- ce qui doit changer pour que ce fichier puisse changer de verdict.
#: Les deux globs sont posés depuis une MESURE, pas par facilite :
#:   * `scripts/python/engine/**/*.py` : importer `engine.runner.abilities.targeting` charge
#:     **200** modules `engine.*` (mesure du 2026-08-07) -- nommer moins serait un faux vert ;
#:   * `scripts/python/*.py` : la cascade `conftest.py` de CE repertoire importe, au niveau
#:     module, **seize** probes de la racine (`tests/engine/runner/conftest.py`) plus six autres
#:     (`tests/engine/conftest.py`), donc le verdict de tout test place ici en depend.
#: Les deux entrees hors `scripts/python/` sont HERITEES de cette meme cascade (les probes
#: qu'elle importe lisent le catalogue et la seed), pas du corps de ce fichier.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
        "frida/hooks/data/ability-names.ts", "data/seed-bc.json",
        # L'etage 1 LIT cette table -- aucun glob ci-dessus ne la couvre.
        "data/symbols/*/metadata/interface_slots.tsv",
    ),
    "build": True,
    "toujours": False,
    "raison": "`build: True` parce que l'etage 1 confronte le prefixe a la table de metadonnee du "
              "build (`interface_slots.tsv`) : un changement de binaire peut renumeroter le slot. "
              "Les etages 2 a 5 sont purement offline (aucun runner, aucun RPC) et ne lisent que "
              "le foyer `runner.components.is_turn_of_unit` et son unique consommateur.",
}

import os                                                                # noqa: E402
import sys                                                               # noqa: E402
from pathlib import Path                                                 # noqa: E402

import pytest                                                            # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities import targeting as T                       # noqa: E402
from engine.runner.abilities.targeting import (TargetingOptions,         # noqa: E402
                                               get_invalid_caster_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.components import (OwnerComponent, set_moved_flag,    # noqa: E402
                                      unit_has_moved)
from engine.runner.snapshot import load_state                            # noqa: E402

# ⚠ L'IMPORT DU FOYER EST FAIT **DANS** SES TESTS, PAS EN TETE, et c'est la seule raison :
# `engine.runner.components.is_turn_of_unit` n'existe pas sur l'arbre TEMOIN (`origin/master`
# d'avant la tranche), donc en tete il fait echouer la **COLLECTE** et la vue rouge se reduit a
# UNE ligne d'`ImportError` au lieu d'une ventilation par etage. Meme motif que
# `test_287r11r1r1_caster_has_2_turns_left_offline.py`.

#: `<racine>/scripts/python/tests/engine/runner/<ce fichier>` -> CINQ remontees.
RACINE = Path(__file__).resolve().parents[5]

COLS, ROWS = 5, 5
CASTER, FOE = 10, 20
#: Les deux joueurs du montage. `PLAYER_MOI` possede le caster ; le tour bascule entre les deux.
PLAYER_MOI, PLAYER_ADVERSE = 3, 4

#: Ce que le probe a MESURE live (`MC1_67`, seed 777, runner `--no-ai`), sur DEUX couples
#: (ability, porteur) a masques DIFFERENTS : `1163 BlackRage` / `bloodDeathCompany` (`0x106004012`)
#: et `1153 HammerOfWrath` / `bloodIntercessor` (`0x102004032`). Le prefixe ne depend ni de
#: l'ability ni de son masque -- deux couples le montrent, un seul ne le montrerait pas.
#: Le ROLE est DERIVE du substrat, jamais de l'ordre des gestes :
#:   `temoin`       -- n'a pas bouge                 -> `0x0` partout ;
#:   `arme`         -- a bouge ET c'est son tour     -> `CasterHasNotMoved`, port inchange ;
#:   `discriminant` -- a bouge ET ce n'est PAS son tour -> natif `0x0`, AVANT `0x10`, APRES `0x0`.
#: `(role, natif, port APRES, port AVANT, has_moved, is_turn_of_unit)`. Grave ici parce qu'un
#: mirror re-genere redeviendrait vert sans que le comportement mesure soit encore le meme.
MESURE_LIVE = (
    ("temoin (n'a pas bouge)", 0x0, 0x0, 0x0, False, True),
    ("arme (a bouge, son tour)", 0x10, 0x10, 0x10, True, True),
    ("discriminant (a bouge, PAS son tour)", 0x0, 0x0, 0x10, True, False),
)


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


def _state(current_player=PLAYER_MOI, caster_owner=PLAYER_MOI):
    """`State` runner minimal : le caster (joueur `caster_owner`) et un ennemi.

    `decisionView.units[].owner` est `OwnerComponent.<PlayerEntityId @+0x10>` -- le proprietaire
    d'ORIGINE, celui que `EntityExtensions$$GetOriginalOwnerEntity` resout (lu dans
    `frida/hooks/game/match-state.ts`, `ownerPlayerId: 0x10`)."""
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": current_player, "units": [
        {"id": CASTER, "visualId": "bloodDeathCompany", "alive": True, "team": 1,
         "owner": caster_owner, "pos": {"col": 0, "row": 2}, "effects": []},
        {"id": FOE, "visualId": "necroWarden", "alive": True, "team": 2,
         "owner": PLAYER_ADVERSE, "pos": {"col": 4, "row": 4}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    return load_state(decision, observe, board=board)


class _AbilityAvecBit:
    """Porteur MINIMAL du bit `CasterHasNotMoved` -- il ne transporte que le masque.

    Deliberement PAS une entree d'`ABILITY_CLASSES` : ce fichier garde le PREFIXE, pas le registre
    (dont les masques sont deja gardes par `probe_181` / `probe_429`), et un porteur factice rend
    l'etage independant de toute renumerotation d'ability."""
    TARGETING_OPTIONS = TargetingOptions(rules=TR.CasterHasNotMoved)


class _AbilitySansBit:
    """Meme forme, bit ABSENT : la BORNE de l'etage 4."""
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy)


# =================================================================================================
# ETAGE 1 -- LE SLOT ET SON ARITE : `IBattleQuery 53 IsTurnOfUnit 1`
# =================================================================================================

def _slots_ibattlequery() -> list:
    """Les lignes `IBattleQuery` d'`interface_slots.tsv` :
    `<interface>\\t<slot DECIMAL>\\t<nom>\\t<arite>\\t<token>`."""
    tsvs = sorted((RACINE / "data" / "symbols").glob("*/metadata/interface_slots.tsv"))
    if not tsvs:
        pytest.skip("aucune table `metadata/interface_slots.tsv` sous data/symbols")
    out: list = []
    for tsv in tsvs:
        rows = []
        for line in tsv.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 4 and parts[0] == "IBattleQuery":
                rows.append((int(parts[1]), parts[2], int(parts[3])))
        if rows:
            out = rows
    return out


def test_slot_0x35_est_is_turn_of_unit_arite_1():
    """`<IBattleQuery slot 0x35>` = 53 = `IsTurnOfUnit`, arite **1**.

    C'est l'appariement que le decompile impose : le call-site de
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` passe UN seul argument
    (`caster`), et la lambda du decorateur
    `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass86_0$$
    u003CIsTurnOfUnitu003Eb__0` relaie le MEME couple (slot, classe d'interface)."""
    rows = _slots_ibattlequery()
    assert rows, "table `IBattleQuery` vide"
    par_slot = {s: (n, a) for (s, n, a) in rows}
    assert 0x35 in par_slot, "le slot 53 est absent de la table"
    nom, arite = par_slot[0x35]
    assert nom == "IsTurnOfUnit", "slot 0x35 = %r, attendu `IsTurnOfUnit`" % (nom,)
    assert arite == 1, "arite du slot 0x35 = %d, le call-site n'en passe qu'UN" % arite


# =================================================================================================
# ETAGE 2 -- LE MIRROR : ses CINQ issues
# =================================================================================================

def test_mirror_rend_true_quand_c_est_le_tour_du_proprietaire():
    from engine.runner.components import is_turn_of_unit
    st = _state(current_player=PLAYER_MOI, caster_owner=PLAYER_MOI)
    assert is_turn_of_unit(st, CASTER) is True


def test_mirror_rend_false_quand_ce_n_est_pas_le_tour_du_proprietaire():
    """LE FAIT DE LA TRANCHE : `GetOriginalOwnerEntity(caster).Id != turn.CurrentPlayerId`."""
    from engine.runner.components import is_turn_of_unit
    st = _state(current_player=PLAYER_ADVERSE, caster_owner=PLAYER_MOI)
    assert is_turn_of_unit(st, CASTER) is False


def test_mirror_rend_false_sur_entite_absente():
    """Mirror du `if (UnitExtensions.GetUnit(unit, state) == null) return false;` natif."""
    from engine.runner.components import is_turn_of_unit
    st = _state()
    assert is_turn_of_unit(st, 9999) is False


def test_mirror_rend_none_quand_le_proprietaire_n_est_pas_capte():
    """`OwnerComponent` absent OU `player` a `None` -> PAS MESURE, jamais un `False` fabrique.

    Le second cas n'est pas theorique : `decisionView` publie `owner` a `null` pour toute unite
    hors plateau sous un `ATeleportingEffect` (mesure #425/#448-r1)."""
    from engine.runner.components import is_turn_of_unit
    st = _state()
    ent = st.get_entity(CASTER)
    ent.get_component(OwnerComponent).player = None
    assert is_turn_of_unit(st, CASTER) is None

    st2 = _state()
    st2.get_entity(CASTER).remove_component(OwnerComponent)
    assert is_turn_of_unit(st2, CASTER) is None


def test_mirror_rend_none_quand_le_joueur_courant_n_est_pas_capte():
    """`State.current_player_id` a `None` = toute fixture construite hors `load_state`."""
    from engine.runner.components import is_turn_of_unit
    st = _state()
    st.current_player_id = None
    assert is_turn_of_unit(st, CASTER) is None


# =================================================================================================
# ETAGE 3 -- LE CABLAGE, ET LA DIRECTION DU TRI-ETAT
# =================================================================================================

def test_clause_evaluee_quand_c_est_le_tour_du_caster():
    """Prefixe VRAI + `Moved` pose -> `CasterHasNotMoved`. C'est le comportement d'AVANT, conserve."""
    st = _state(current_player=PLAYER_MOI, caster_owner=PLAYER_MOI)
    set_moved_flag(st, CASTER)                     # `UnitExtensions$$SetMovedFlag`
    assert unit_has_moved(st, CASTER) is True
    assert int(get_invalid_caster_reason(st, CASTER, _AbilityAvecBit())) \
        == int(TR.CasterHasNotMoved)


def test_clause_SAUTEE_quand_ce_n_est_pas_le_tour_du_caster():
    """LE FIX. Prefixe FAUX -> le natif saute la clause ENTIERE, flag `Moved` compris.

    Sans le prefixe le port rendait `CasterHasNotMoved` : un ecart RESTRICTIF (il refusait un cast
    que le natif accepte)."""
    st = _state(current_player=PLAYER_ADVERSE, caster_owner=PLAYER_MOI)
    set_moved_flag(st, CASTER)
    assert unit_has_moved(st, CASTER) is True, "le montage doit VRAIMENT poser le flag"
    assert int(get_invalid_caster_reason(st, CASTER, _AbilityAvecBit())) == 0


def test_non_mesure_NE_SOULAGE_PAS_la_clause():
    """LA DIRECTION DU TRI-ETAT EST LE LIVRABLE. `None` = substrat non capte -> la clause reste
    evaluee. Sauter sur une non-mesure FABRIQUERAIT une acceptation ; la garder rend exactement le
    verdict d'avant ce prefixe. C'est l'inverse de la convention du module DECISION
    (`services.ability_caster_gates.invalid_caster_reason`), et pour la raison qui l'inverse :
    la-bas le tri-etat borne la ZONE par le HAUT, ici il garde un REFUS mesure."""
    from engine.runner.components import is_turn_of_unit
    st = _state()
    set_moved_flag(st, CASTER)
    st.current_player_id = None
    assert is_turn_of_unit(st, CASTER) is None
    assert int(get_invalid_caster_reason(st, CASTER, _AbilityAvecBit())) \
        == int(TR.CasterHasNotMoved)


# =================================================================================================
# ETAGE 4 -- LA BORNE : sans le bit, le prefixe n'est JAMAIS consulte
# =================================================================================================

def test_ability_sans_le_bit_ne_consulte_jamais_le_prefixe(monkeypatch):
    """`if (rules & 0x10)` est le PREMIER terme du natif : le prefixe vit SOUS lui.

    Le compteur est la contre-epreuve : sans lui, un port qui appellerait le prefixe d'abord
    passerait ce test par coincidence (les deux verdicts valent 0)."""
    appels = []
    monkeypatch.setattr(T, "is_turn_of_unit",
                        lambda *a, **k: appels.append(a) or True)
    st = _state()
    set_moved_flag(st, CASTER)
    assert int(get_invalid_caster_reason(st, CASTER, _AbilitySansBit())) == 0
    assert appels == [], "le prefixe a ete consulte alors que le bit n'est PAS pose"
    # ... et il l'est des que le bit est la : le compteur MESURE, il ne decore pas.
    assert int(get_invalid_caster_reason(st, CASTER, _AbilityAvecBit())) \
        == int(TR.CasterHasNotMoved)
    assert len(appels) == 1


# =================================================================================================
# ETAGE 5 -- LE GRAVAGE DE LA MESURE LIVE, ET SON MUTANT
# =================================================================================================

def test_les_trois_bras_de_la_mesure_live_sont_reproduits_offline():
    """Chaque bras du probe est rejoue sur un `State` de fixture portant LE MEME substrat
    (`has_moved`, `is_turn_of_unit`). Les verdicts NATIFS graves doivent etre ceux que le port
    rend -- c'est la confrontation, transposee offline."""
    from engine.runner.components import is_turn_of_unit
    for (bras, natif, apres, _avant, moved, itou) in MESURE_LIVE:
        cur = PLAYER_MOI if itou else PLAYER_ADVERSE
        st = _state(current_player=cur, caster_owner=PLAYER_MOI)
        if moved:
            set_moved_flag(st, CASTER)
        assert unit_has_moved(st, CASTER) is moved, bras
        assert is_turn_of_unit(st, CASTER) is itou, bras
        got = int(get_invalid_caster_reason(st, CASTER, _AbilityAvecBit()))
        assert got == natif == apres, (
            "%s : port %#x, mesure live natif %#x / apres %#x" % (bras, got, natif, apres))


def test_le_mutant_prefixe_toujours_vrai_est_SEPARE_par_le_bras_hors_tour(monkeypatch):
    """Le MUTANT = l'etat de `master` avant la tranche : la clause evaluee inconditionnellement.

    Il doit RATER au moins un bras, sinon la tranche n'aurait rien change et la mesure live ne
    prouverait rien. Le test ASSERTIONNE SON PROPRE NON-VIDE : un ensemble de bras separateurs
    VIDE serait un vert qui ne mesure rien."""
    from engine.runner.components import is_turn_of_unit
    monkeypatch.setattr(T, "is_turn_of_unit", lambda *a, **k: True)
    separateurs = []
    for (bras, natif, _apres, avant, moved, itou) in MESURE_LIVE:
        cur = PLAYER_MOI if itou else PLAYER_ADVERSE
        st = _state(current_player=cur, caster_owner=PLAYER_MOI)
        if moved:
            set_moved_flag(st, CASTER)
        got = int(get_invalid_caster_reason(st, CASTER, _AbilityAvecBit()))
        assert got == avant, (
            "%s : le mutant rend %#x, la mesure live donnait AVANT = %#x" % (bras, got, avant))
        if got != natif:
            separateurs.append(bras)
    assert separateurs, (
        "AUCUN bras ne separe le mutant du natif -- le montage ne mesure rien")
    assert "discriminant (a bouge, PAS son tour)" in separateurs
    # Et le foyer est bien RESTAURE apres le monkeypatch (sinon les tests suivants mesureraient
    # le mutant sans le savoir).
    assert is_turn_of_unit is not None
