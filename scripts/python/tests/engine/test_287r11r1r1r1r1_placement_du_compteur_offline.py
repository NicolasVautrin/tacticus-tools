"""#287-r11-r1-r1-r1-r1 -- GARDE du PLACEMENT de `State.turn_counts` (`TurnComponent+0x38`, les
tours DEMARRES par joueur).

L'ECRIVAIN NATIF EST UNIQUE, et ce n'est pas celui ou le port l'avait mis.
`IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer` ecrit les DEUX dictionnaires --
relu verbatim sur le build courant :

    if (get_CurrentPlayerId() == nextPlayerId)  return;                    // NO-OP, AVANT tout bump
    if (!started.ContainsKey(next))             started.Add(next, 0);
    if (get_CurrentPlayerId() != 0) { ended.TryAdd(cur, 0); ended[cur] += 1; }
    prev = get_CurrentPlayerId();
    <+0x24> = nextPlayerId;  <+0x18> = prev;
    started[get_CurrentPlayerId()] += 1;                                   // l'ENTRANT

`IdunBattle.Operations.StartTurnOperation$$Execute`, lui, ne fait que **LIRE**
`GetAmountOfTurnsStartedByCurrentPlayer` (il le compare a `1`). Le port y bumpait pourtant
`turn_counts` -- placement HERITE, mesure comme faux par #287-r11-r1-r1-r1.

CE QUE LE PLACEMENT CHANGE, ET OU. Les deux sites sont ENCHAINES par `advance_turn` (`ChangeTurn`
puis `StartTurn`), donc l'etat observable apres la paire etait le meme -- SAUF sur le **NO-OP**
(`cur == next`, seul joueur encore jouable), ou le natif ne compte RIEN et le port comptait un tour
de plus. Direction : le port SUR-comptait, dans ce seul regime.

CE QUI L'AVAIT LAISSE EN PLACE : huit sites (tous des probes) appellent
`StartTurnOperation.execute` SEUL, sans `ChangeTurn`. Leur appel ne fait plus avancer le compteur.
L'etage 5 le MESURE plutot que de l'affirmer -- aucun de ces fichiers ne lit `turn_counts` ni l'un
de ses deux consommateurs portes.

⚠ NON CONFRONTE LIVE, POUR UNE RAISON NOMMEE : le regime NO-OP suppose qu'il ne reste qu'UN joueur
jouable, ce qui termine le match (`StateExtensions.IsMatchFinished`, tete de `FindNextPlayer`). Le
NO-OP est donc LU au decompile, pas monte en bataille. Ce qui EST confronte live, c'est la
NON-REGRESSION du regime nominal (alternance stricte) : `probe_287r11r1r1_caster_has_2_turns_left.py`
relit le verdict natif de `HasMinimumRemainingTurns` a chaque pas, et son bras `bascule` lit les
compteurs du port sans qu'on les lui souffle.

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
        # PROPRE A CE FICHIER, pris LARGE : le flux de tour traverse
        # `runner/operations/turnflow.py`, `runner/snapshot.py` (le seed des deux dicts),
        # `services/battle_query.py` (leurs lecteurs) et les vecteurs de triggers de tour.
        "scripts/python/engine/**/*.py",
        # L'ETAGE 5 lit les PROBES qui appellent `StartTurnOperation.execute` seul : leur contenu
        # decide de son verdict, donc ils sont dans le declencheur. Le glob est LARGE parce que le
        # recensement l'est : il balaye `probe_*.py` et doit rougir si un probe NEUF appelle
        # l'operation ET lit `turn_counts`.
        "scripts/python/probe_*.py",
        # LA CASCADE DES CONFTEST, mesuree (`probe_486r15`), pas devinee : tout fichier de
        # `tests/engine/` traine ces modules racine par la seule cascade des conftest, sans en
        # toucher aucun (residu #531).
        "scripts/python/board.py", "scripts/python/catalog_inject.py",
        "scripts/python/engine_agreement_stages.py", "scripts/python/engine_validate.py",
        "scripts/python/hexgeo.py", "scripts/python/host_inputs.py",
        "scripts/python/rl_collect_batch.py", "scripts/python/stream_events.py",
        "scripts/python/symbols_layout.py", "scripts/python/unit_map.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE du PLACEMENT d'un ecrivain (quelle fonction native ecrit quel champ). "
              "Aucun RPC, aucun runner : le regime discriminant (NO-OP) termine le match, donc il "
              "est LU au decompile ; la non-regression live vit dans "
              "`probe_287r11r1r1_caster_has_2_turns_left.py`.",
}

import pathlib                                                              # noqa: E402
import re                                                                   # noqa: E402

from engine.runner.components import (OwnerComponent, StatsComponent,       # noqa: E402
                                      UnitComponent, UnitFlagsComponent)
from engine.runner.operations import turnflow as TF                         # noqa: E402
from engine.runner.state import State                                       # noqa: E402
from engine.entities.stats import StatType                                  # noqa: E402
from engine.entities.unit_context import UnitContext                        # noqa: E402

PYDIR = pathlib.Path(__file__).resolve().parents[2]


def _etat(specs, cur):
    """`State` synthetique : `specs` = [(joueur, nb_vivantes), ...]. Un joueur a `0` vivante n'a
    AUCUNE entite, donc il n'entre pas dans `player_turn_order` (qui derive des proprietaires
    d'unites) -- c'est ainsi qu'on monte le regime NO-OP."""
    st = State()
    st.current_player_id = cur
    uid = 100
    for pl, vivantes in specs:
        for _ in range(vivantes):
            uid += 1
            e = st.add_entity(uid)
            e.add_component(OwnerComponent(team=pl, player=pl))
            e.add_component(UnitComponent(visual_id="u%d" % uid, alive=True))
            e.add_component(UnitFlagsComponent())
            e.add_component(StatsComponent(
                ctx=UnitContext(entity_id=uid, visual_id="u%d" % uid, traits=[])))
    return st


# =================================================================================================
# ETAGE 1 -- L'ECRIVAIN : `SetCurrentPlayer` ecrit les DEUX dicts, sur DEUX joueurs differents
# =================================================================================================

def test_set_current_player_bumpe_l_ENTRANT_pour_les_demarres():
    """`started[get_CurrentPlayerId()] += 1` est la DERNIERE instruction, et `get_CurrentPlayerId()`
    vaut deja `nextPlayerId` a ce point. Le jumeau `ended`, lui, porte sur le SORTANT.

    Les deux sont assertionnes ENSEMBLE : un port qui les bumperait sur le MEME joueur passerait un
    test qui n'en regarderait qu'un."""
    st = _etat([(3, 2), (4, 2)], 3)
    TF.set_current_player(st, 4)
    assert st.turn_counts == {4: 1}, "les DEMARRES vont a l'ENTRANT (4)"
    assert st.turns_ended == {3: 1}, "les TERMINES vont au SORTANT (3)"
    TF.set_current_player(st, 3)
    assert st.turn_counts == {4: 1, 3: 1} and st.turns_ended == {3: 1, 4: 1}


def test_le_bump_des_demarres_est_INCONDITIONNEL_meme_depuis_le_joueur_ZERO():
    """Le gate `if (get_CurrentPlayerId() != 0)` du decompile porte UNIQUEMENT sur `ended`. Le bump
    de `started` est en dehors : partir de « aucun joueur actif » compte quand meme un tour DEMARRE
    pour l'entrant."""
    st = _etat([(3, 2), (4, 2)], 0)
    TF.set_current_player(st, 3)
    assert st.turns_ended == {}, "le joueur 0 ne doit JAMAIS entrer au dict des TERMINES"
    assert st.turn_counts == {3: 1}, "mais l'ENTRANT compte bien un tour DEMARRE"


# =================================================================================================
# ETAGE 2 -- LE NO-OP : `if (cur == next) return;` precede les DEUX bumps
# =================================================================================================

def test_le_NO_OP_ne_bumpe_AUCUN_des_deux_dicts():
    """Et le test assertionne son propre NON-VIDE : le meme etat, hors NO-OP, doit bouger. Sans ce
    second bras, un port qui ne bumperait JAMAIS `turn_counts` passerait."""
    st = _etat([(3, 2)], 3)
    st.turn_counts, st.turns_ended = {3: 5}, {3: 4}
    TF.set_current_player(st, 3)
    assert st.turn_counts == {3: 5} and st.turns_ended == {3: 4}, (
        "le retour anticipe est AVANT les deux bumps")
    TF.set_current_player(st, 4)
    assert st.turn_counts == {3: 5, 4: 1} and st.turns_ended == {3: 5}, (
        "regime NON separant : hors NO-OP les deux dicts doivent bouger")


def test_change_turn_sur_un_seul_joueur_jouable_ne_compte_RIEN():
    """`FindNextPlayer` rend le joueur COURANT quand c'est le seul jouable -> `SetCurrentPlayer`
    est un NO-OP. C'est le regime que le port SUR-comptait."""
    st = _etat([(3, 2)], 3)
    st.turn_counts = {3: 5}
    assert TF.ChangeTurnOperation.execute(st) == 3
    assert st.turn_counts == {3: 5} and st.turns_ended == {}


# =================================================================================================
# ETAGE 3 -- `StartTurnOperation` n'ECRIT PAS `+0x38`, et continue d'ecrire ce qu'il doit
# =================================================================================================

def test_start_turn_n_ecrit_PAS_le_dict_des_demarres():
    st = _etat([(3, 2), (4, 2)], 3)
    st.turn_counts = {3: 7}
    TF.StartTurnOperation.execute(st, 3)
    assert st.turn_counts == {3: 7}, (
        "`StartTurnOperation$$Execute` ne fait que LIRE `GetAmountOfTurnsStartedByCurrentPlayer`")


def test_start_turn_ecrit_TOUJOURS_le_compteur_PER_UNITE():
    """NON-REGRESSION : le deplacement ne doit pas emporter le compteur PER-UNITE
    `turnsStarted@+0x58` (stat 12), qui lui EST bien ecrit par cette operation. Les deux compteurs
    sont distincts et les confondre decale toute phase de cycle."""
    st = _etat([(3, 1)], 3)
    uid = next(iter(st.entities))
    us = st.get_entity(uid).get_component(StatsComponent).ctx.stats
    avant = int(us.get_stat(int(StatType.TURNS_STARTED), 0) or 0)
    TF.StartTurnOperation.execute(st, 3)
    apres = int(us.get_stat(int(StatType.TURNS_STARTED), 0) or 0)
    assert apres == avant + 1, ("la stat 12 doit toujours avancer : %r -> %r" % (avant, apres))


# =================================================================================================
# ETAGE 4 -- LA DIVERGENCE, PAR LE CHEMIN REEL (`advance_turn`), ET SON MUTANT
# =================================================================================================

def _placement_avant(monkeypatch):
    """LE PORT D'AVANT #287-r11-r1-r1-r1-r1, reproduit en DEUX moities -- c'est ce qui le rend
    fidele : `set_current_player` SANS son bump de `turn_counts`, et `StartTurnOperation.execute`
    AVEC. Ne reproduire qu'une moitie donnerait soit un double comptage, soit aucun."""
    orig_start = TF.StartTurnOperation.execute

    def scp_avant(state, next_player_id):
        cur = state.current_player_id
        if cur is not None and int(cur) == int(next_player_id):
            return
        if cur is not None and int(cur) != 0:
            state.turns_ended[int(cur)] = int(state.turns_ended.get(int(cur), 0)) + 1
        state.current_player_id = next_player_id

    def start_avant(state, player):
        state.turn_counts[player] = state.turn_counts.get(player, 0) + 1
        return orig_start(state, player)

    monkeypatch.setattr(TF, "set_current_player", scp_avant)
    monkeypatch.setattr(TF.StartTurnOperation, "execute", staticmethod(start_avant))


def test_sur_le_NO_OP_advance_turn_ne_compte_RIEN():
    """Le chemin REEL : `EndTurnOperation.execute(advance=True)` enchaine `ChangeTurn` puis
    `StartTurn`. Sur le NO-OP, ni l'un ni l'autre ne doit compter."""
    st = _etat([(3, 2)], 3)
    st.turn_counts = {3: 5}
    r = TF.EndTurnOperation.execute(st, advance=True)
    assert r["next_player"] == 3, "le montage doit bien exercer le NO-OP"
    assert st.turn_counts == {3: 5}, "le natif ne compte AUCUN tour dans ce regime"


def test_le_placement_d_avant_SUR_COMPTAIT_sur_le_NO_OP(monkeypatch):
    """CONTRE-EPREUVE du precedent : sous le placement HERITE, le meme etat gagne un tour. Si les
    deux rendaient la meme chose, la tranche ne changerait aucun observable."""
    _placement_avant(monkeypatch)
    st = _etat([(3, 2)], 3)
    st.turn_counts = {3: 5}
    TF.EndTurnOperation.execute(st, advance=True)
    assert st.turn_counts == {3: 6}, (
        "le port d'avant devait SUR-compter ici -- sinon le cliquet ci-dessus ne garde rien")


def test_hors_NO_OP_les_deux_placements_COINCIDENT(monkeypatch):
    """L'autre moitie du fait, et elle compte autant : le deplacement ne doit RIEN changer au
    regime nominal (alternance stricte). C'est ce qui autorise a ne pas re-confronter live tout le
    flux de tour."""
    ref = _etat([(3, 2), (4, 2)], 3)
    ref.turn_counts = {3: 1}
    for _ in range(4):
        TF.EndTurnOperation.execute(ref, advance=True)
    attendu = dict(ref.turn_counts)

    _placement_avant(monkeypatch)
    old = _etat([(3, 2), (4, 2)], 3)
    old.turn_counts = {3: 1}
    for _ in range(4):
        TF.EndTurnOperation.execute(old, advance=True)
    assert dict(old.turn_counts) == attendu, (
        "hors NO-OP les deux placements doivent coincider : %r vs %r"
        % (dict(old.turn_counts), attendu))
    assert sum(attendu.values()) > 1, "regime DEGENERE : aucun tour n'a ete compte"


def test_l_identite_des_deux_dicts_tient_sous_advance_turn():
    """`ended[p] == started[p] - (p == CurrentPlayerId ? 1 : 0)` -- le SEUL fondement du seed
    (`snapshot._load_turns_ended`). Le deplacement du bump la met en jeu : les deux dicts sont
    desormais ecrits par la MEME fonction, donc une erreur d'ordre s'y verrait."""
    st = _etat([(3, 2), (4, 2)], 3)
    st.turn_counts = {3: 1}
    for _ in range(6):
        TF.EndTurnOperation.execute(st, advance=True)
        cur = st.current_player_id
        for p, started in st.turn_counts.items():
            attendu = int(started) - (1 if int(p) == int(cur) else 0)
            assert st.turns_ended.get(int(p), 0) == attendu, (
                "identite rompue pour le joueur %d : ended=%r started=%r courant=%r"
                % (p, st.turns_ended.get(int(p)), started, cur))
    assert sum(st.turns_ended.values()) >= 5, "la sequence doit avoir vraiment compte des tours"


# =================================================================================================
# ETAGE 5 -- LES APPELANTS DE `StartTurnOperation.execute` SEUL : le recensement est EXECUTABLE
# =================================================================================================

#: Les deux consommateurs PORTES de `State.turn_counts`, et le champ qui en derive.
#: `PlayerTurnsStarted` (`UnitsPlayerTurnsStartedFormula`) alimente le cycle a 3 temps de
#: `SereneUnifierAbility` ; `turn_defeated` est pose depuis le meme dict et lu par le gate de delai
#: d'`EnvAmbushResurrect`.
_CONSOMMATEURS = ("turn_counts", "PlayerTurnsStarted", "turn_defeated")


def _probes_appelant_start_turn():
    """Les fichiers `probe_*.py` qui appellent `StartTurnOperation.execute`. DERIVE du corpus, pas
    recopie : un probe NEUF entre de lui-meme dans le recensement."""
    out = {}
    for p in sorted(PYDIR.glob("probe_*.py")):
        txt = p.read_text(encoding="utf-8", errors="replace")
        n = len(re.findall(r"StartTurnOperation\.execute\(", txt))
        if n:
            out[p.name] = (n, txt)
    return out


def test_les_appelants_de_start_turn_seul_ne_lisent_AUCUN_consommateur():
    """CE QUE LE DEPLACEMENT LEUR FAIT : leur appel ne fait plus avancer `turn_counts`. C'est sans
    effet tant qu'aucun ne LIT ce dict ni l'un de ses consommateurs -- et c'est ce que ce test
    MESURE, plutot que de le supposer.

    Un probe qui violerait la regle doit jouer la PAIRE (`set_current_player` ou
    `ChangeTurnOperation.execute`, puis `StartTurnOperation.execute`), ce qui est aussi ce que fait
    le natif. Le test assertionne son propre non-vide : un recensement qui ne trouverait plus aucun
    appelant ne garderait rien."""
    trouves = _probes_appelant_start_turn()
    assert trouves, ("aucun probe n'appelle `StartTurnOperation.execute` : le recensement ne garde "
                     "plus rien (glob ou nom de methode change ?)")
    fautifs = {nom: [c for c in _CONSOMMATEURS if c in txt]
               for nom, (_n, txt) in trouves.items()}
    fautifs = {k: v for k, v in fautifs.items() if v}
    assert not fautifs, (
        "ces probes appellent `StartTurnOperation.execute` ET lisent un consommateur de "
        "`turn_counts` -- ils doivent jouer la PAIRE : %r" % fautifs)


def test_le_recensement_des_appelants_est_NON_TRIVIAL():
    """Anti-vacuite du precedent : le corpus doit reellement contenir des appels, et le motif
    cherche doit reellement apparaitre. Un `_CONSOMMATEURS` dont aucun terme n'existe nulle part
    ferait passer le test ci-dessus pour vert sans rien verifier."""
    trouves = _probes_appelant_start_turn()
    total = sum(n for n, _txt in trouves.values())
    assert total >= 5, ("le recensement doit porter sur plusieurs sites : %d appel(s) dans %d "
                        "fichier(s)" % (total, len(trouves)))
    # Chaque nom cherche doit EXISTER dans le moteur : un terme disparu (renomme) ferait passer le
    # filtre du test precedent pour vert sans rien verifier. Le corpus est le paquet `engine`
    # entier -- c'est ce que les probes importent.
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                       for p in (PYDIR / "engine").rglob("*.py"))
    manquants = [c for c in _CONSOMMATEURS if c not in corpus]
    assert not manquants, ("ces noms de consommateurs n'existent plus dans `engine/` : le filtre "
                           "de l'etage 5 serait vacu -- %r" % manquants)
