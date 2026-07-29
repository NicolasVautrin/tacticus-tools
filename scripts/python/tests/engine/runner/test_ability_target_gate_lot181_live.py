"""#181 -- GARDE des 13 `TARGETING_OPTIONS` du lot (ultramarines / sisterhood / tyranids /
spacewolves / admec / bloodangels), confrontee au NATIF.

CE QUE CE FICHIER PROUVE, ET POURQUOI IL EXISTE
-----------------------------------------------
Un masque `TARGETING_OPTIONS` est une CONSTANTE recopiee d'un decompile. Rien, dans un test qui se
contente de relire cette constante, ne distingue un masque JUSTE d'un masque INVENTE -- et un masque
faux est PIRE que l'absence (il refuse pour la mauvaise raison, au lieu de ne rien refuser). La seule
garde qui vaut confronte le masque au comportement NATIF, et montre que sans lui le moteur offline
acceptait le cast.

Trois assertions, dans cet ordre :

  1. `test_le_natif_refuse_bien_ce_cas`      -- PRECONDITION lue sur l'oracle `abilityReason`
     (masque `TargetingRule` natif). Sans elle, les deux suivantes garderaient du vide.
  2. `test_sans_masque_le_moteur_acceptait`  -- LE ROUGE AVANT : la MEME ability, privee de ses
     `TARGETING_OPTIONS` (= son etat sur `master` avant #181), rend 0 = CAST ACCEPTE. C'est la
     mesure de ce que le lot corrige, pas une affirmation.
  3. `test_avec_masque_le_moteur_refuse_pour_la_meme_raison` -- le port refuse, et avec le MEME
     code que le natif (pas seulement « refuse »).

Le contrat de fidelite de `case-115` §3 est conserve tel quel :

    natif == 0   =>  port == 0                          (le port n'invente aucun refus)
    natif != 0   =>  port == natif  (regle PORTEE)  ou  port == 0  (regle NON PORTEE, permissif)
    jamais       :   port != 0 et port != natif

Le sens PERMISSIF (« aucun refus invente ») reste garde par
`test_le_port_ne_refuse_jamais_ce_que_le_natif_accepte` et par `test_aucun_refus_pour_la_mauvaise_
raison`, qui balaient TOUTES les cibles vivantes -- pas par une ligne du parametrage.

⚠ Le cas `HEALABLE_1002` a CHANGE DE COLONNE (#254, au rebase). Il encodait « regle NON portee ->
port == 0 », donnee vraie a son ecriture ; **#245 a porte `TargetIsHealable`** (bit 8, predicat
`attack_query.entity_can_be_healed`, slot 0x11 d'`IAttackQuery`). Ce test etait alors INJOUABLE --
son roster porte `ultraInceptorSgt`, et tout `rl_duel build` qui le contenait rendait
« initAndStart: system error » (cf. `docs/rl/case-254-build-migration-blockers.md`) : les 26 cas
partaient en ERROR, donc le merge de #245 n'a pas pu voir la ligne devenue fausse. MESURE au
deblocage : natif `0x100 TargetIsHealable`, port `0x100` -- accord parfait, seul l'attendu etait
perime.

DEUX PROFILS DE PORTEE distincts sont exerces, parce que `range` se pose dans le MEME appel de ctor
que `rules` et se trompe aussi silencieusement -- et c'est le sens qui casse VRAIMENT (une portee
trop courte refuse des casts LEGAUX) :

  * `RANGE_ADJACENT` (`override_range=1`, portee 1) -- GreatFrostAxe 1089, CombatRestoratives 1002,
    DeathFromAbove 1003 ;
  * `RANGE_ADJACENT_IF_MELEE_CASTER` (`override_range=None` -> portee d'ARME) -- MortisRound 1004,
    un AUTRE chemin de `get_range` (`unit_weapon_range`), pas un litteral.

Les deux profils sont DISCRIMINES sur des casters qui portent tous une arme RANGED r3 : 1003 et 1004
ne different que par leur `TargetingRange`, et le natif les traite differemment (mesure
`probe_181_range_discriminant.py` : 1003 n'accepte QU'A distance 1, 1004 accepte encore a 2).
Intervertir les deux `range` serait donc VU ici.

PORTEURS (gate de confrontabilite -- tous HERO, presents dans `rl_duel.py --list-pool`) :
`spaceWulfen` (Ulf, 1089), `ultraApothecary` (Incisus, 1002), `ultraEliminatorSgt` (Certus, 1004),
`ultraInceptorSgt` (Bellator, 1003).

HORS PERIMETRE, et pourquoi : les deux abilities MoW du lot (`ThriceBlessedConflagration` 1187,
`DevastatingRefrain` 1188, porteur `adeptExorcist`). `abilityReason` rend `ValidRequest` (0x1) pour
un caster MoW -- la requete est rejetee en AMONT de la cascade de ciblage, l'oracle ne descend donc
jamais jusqu'au masque. Leur masque reste confirme par `decisionView` au build (1187 n'offre QUE les
3 allies, sur TOUT le plateau = `TargetIsFriendly` + `UseWholeBoard` ; 1188 n'offre QUE des tuiles =
`TargetIsTile`), mais ce n'est pas assertable ici.

ASCII only. Skip propre si pas de session / geometrie non cooperative.
"""
from __future__ import annotations

import os

import pytest

from engine.entities.pathfinding.board import Board
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import is_invalid_target
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.snapshot import load_state

ULF = "spaceWulfen"                 # 1089 GreatFrostAxe   -- preset TO+0x40, RANGE_ADJACENT
INCISUS = "ultraApothecary"         # 1002 CombatRestoratives -- flags directs, RANGE_ADJACENT
CERTUS = "ultraEliminatorSgt"       # 1004 MortisRound     -- preset TO+0x80, portee d'ARME
BELLATOR = "ultraInceptorSgt"       # 1003 DeathFromAbove  -- flags directs, RANGE_ADJACENT
FOES = "orksWarboss,orksNob"
BOARD = os.environ.get("GATE181_BOARD", "MC1_67")
SEED = os.environ.get("GATE181_SEED", "777")

GREAT_FROST_AXE = 1089
COMBAT_RESTORATIVES = 1002
MORTIS_ROUND = 1004
DEATH_FROM_ABOVE = 1003


# --- les cas, chacun = (ability, role du caster, role de la cible, regle NATIVE attendue,
#     regle attendue du PORT). Le 5e champ vaut 0 quand la regle native n'est PAS portee.
CAS = [
    ("ENEMY_1089", GREAT_FROST_AXE, ULF, "ally", TR.TargetIsEnemy, TR.TargetIsEnemy),
    ("RANGE_1089", GREAT_FROST_AXE, ULF, "foe", TR.TargetIsInRange, TR.TargetIsInRange),
    ("FRIENDLY_1002", COMBAT_RESTORATIVES, INCISUS, "foe", TR.TargetIsFriendly, TR.TargetIsFriendly),
    # `TargetIsHealable` (0x100, dans le masque 0x8500) est PORTEE depuis #245 -- predicat =
    # `attack_query.entity_can_be_healed`, mirror du slot 0x11 d'`IAttackQuery`. Le port doit donc
    # rendre EXACTEMENT la raison native, comme toute regle portee.
    ("HEALABLE_1002", COMBAT_RESTORATIVES, INCISUS, "ally", TR.TargetIsHealable, TR.TargetIsHealable),
    ("ENEMY_1004", MORTIS_ROUND, CERTUS, "ally", TR.TargetIsEnemy, TR.TargetIsEnemy),
    ("RANGE_1004", MORTIS_ROUND, CERTUS, "foe", TR.TargetIsInRange, TR.TargetIsInRange),
    ("ENEMY_1003", DEATH_FROM_ABOVE, BELLATOR, "ally", TR.TargetIsEnemy, TR.TargetIsEnemy),
    # 1003 est le cas ou se serait vue une erreur sur `range` : `ultraInceptorSgt` porte une arme
    # RANGED r3, mais son masque impose `RANGE_ADJACENT` (portee 1). Mesure `probe_181_range_
    # discriminant.py` : le natif refuse `TargetIsInRange` a distance 2 et n'accepte QU'A 1 --
    # ce n'est donc PAS la portee d'arme. Un `RANGE_FROM_CONFIG` mis ici aurait accepte a 3.
    ("RANGE_1003", DEATH_FROM_ABOVE, BELLATOR, "foe", TR.TargetIsInRange, TR.TargetIsInRange),
]
IDS = [c[0] for c in CAS]


def _sans_masque(ability_type: int):
    """L'ability TELLE QU'ELLE ETAIT avant #181 : meme classe, meme behaviour, `TARGETING_OPTIONS`
    absentes. C'est litteralement l'etat de `master` -- `get_invalid_target_reason` commence par
    `getattr(ability, "TARGETING_OPTIONS", None)` et rend 0 des que c'est `None`.

    Sous-classer plutot que patcher l'attribut garde le registre INTACT pour les autres tests."""
    base = ABILITY_CLASSES[ability_type]
    return type("Sans" + base.__name__, (base,), {"TARGETING_OPTIONS": None, "__slots__": ()})()


@pytest.fixture(scope="module")
def gate181(rpc, build_runner):
    """Runner FIGE (aucun cast joue) : trois casters HERO au contact l'un de l'autre, deux ennemis
    hors de portee de tous. On lit l'oracle `abilityReason` pour chaque couple, puis on rejoue le
    gate offline sur le MEME snapshot autant de fois qu'on veut.

    Aucun cast n'est applique : ce fichier ne teste QUE la decision de ciblage, dont les deux faces
    (refus natif / refus offline) sortent en amont de toute behaviour -- donc sans consommer de RNG,
    d'ou l'absence de `dumpRng` ici (contraste `test_ability_target_gate_live.py`, qui teste AUSSI la
    face execution)."""
    rid = build_runner(SEED, extra=["--p-units", f"{ULF},{INCISUS},{CERTUS},{BELLATOR}",
                                    "--a-units", FOES, "--board", BOARD])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    # `native_sym` = le champ `neighbours` du boardGraph, mode CANONIQUE de production : c'est lui
    # qui porte la porte d'ELEVATION de `MovementUtil$$AreTilesAdjacent` (|dElev| < 2), dont depend
    # le volet `only_adjacent` du gate de portee.
    board = Board(bg["tiles"], adjacency="native_sym")

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)

    def find(vis):
        return next((u for u in (dec.get("units") or [])
                     if u.get("visualId") == vis and u.get("alive")), None)

    casters = {v: find(v) for v in (ULF, INCISUS, CERTUS, BELLATOR)}
    if any(u is None for u in casters.values()):
        pytest.skip("un caster du lot est absent/mort au build")
    mine = casters[ULF]["owner"]
    foes = [u for u in (dec.get("units") or [])
            if u.get("alive") and u.get("owner") != mine]
    if not foes:
        pytest.skip("aucun ennemi vivant")

    # Cible AMIE = un allie qui n'est pas le caster ; cible ENNEMIE = le 1er ennemi vivant.
    def role_target(caster_vis, role):
        if role == "foe":
            return foes[0]["id"]
        other = next(v for v in (ULF, INCISUS, CERTUS, BELLATOR) if v != caster_vis)
        return casters[other]["id"]

    native = {}
    for cid, atype, caster_vis, role, _n, _p in CAS:
        cu = casters[caster_vis]["id"]
        tu = role_target(caster_vis, role)
        r = rpc("abilityReason", {"runnerId": rid, "casterId": cu,
                                  "abilityType": atype, "targetId": tu}, 60) or {}
        native[cid] = {
            "caster_id": cu, "target_id": tu,
            "target_hex": int(((r.get("targetReason") or {}).get("hex") or "0x0"), 16),
            "target_names": list((r.get("targetReason") or {}).get("reasons") or []),
            "caster_hex": int(((r.get("casterReason") or {}).get("hex") or "0x0"), 16)}

    # Agrement large : tous les couples (caster du lot x unite vivante), pour le contrat §3.
    alive = [u["id"] for u in (dec.get("units") or []) if u.get("alive")]
    broad = {}
    for atype, caster_vis in ((GREAT_FROST_AXE, ULF), (COMBAT_RESTORATIVES, INCISUS),
                              (MORTIS_ROUND, CERTUS)):
        cu = casters[caster_vis]["id"]
        for uid in alive:
            r = rpc("abilityReason", {"runnerId": rid, "casterId": cu,
                                      "abilityType": atype, "targetId": uid}, 60) or {}
            broad[(atype, cu, uid)] = (
                int(((r.get("targetReason") or {}).get("hex") or "0x0"), 16),
                list((r.get("targetReason") or {}).get("reasons") or []))

    return {"rid": rid, "board": board, "dec": dec, "ob": ob, "snap": snap,
            "native": native, "broad": broad, "alive": alive}


def _state(g):
    return load_state(g["dec"], g["ob"], g["snap"], board=g["board"])


def _port(g, ability, caster_id, target_id) -> int:
    return is_invalid_target(_state(g), int(caster_id), int(target_id), ability)


@pytest.mark.parametrize("cas_id", IDS)
def test_le_natif_refuse_bien_ce_cas(gate181, cas_id):
    """PRECONDITION. Le cas n'a de valeur que si le NATIF refuse -- et pour la raison qu'on croit.
    Lue sur `abilityReason`, jamais supposee : c'est elle qui rend les deux tests suivants
    discriminants plutot que decoratifs."""
    attendu = next(c[4] for c in CAS if c[0] == cas_id)
    n = gate181["native"][cas_id]
    assert n["target_hex"] == int(attendu), (
        "precondition NATIVE non tenue pour %s : attendu %s (%#x), lu %s (%#x)"
        % (cas_id, TR(attendu).name, int(attendu), n["target_names"], n["target_hex"]))


@pytest.mark.parametrize("cas_id", IDS)
def test_sans_masque_le_moteur_acceptait(gate181, cas_id):
    """LE ROUGE AVANT -- ce que #181 corrige, MESURE et non affirme.

    Prive de ses `TARGETING_OPTIONS` (l'etat de `master`), le moteur offline rend 0 sur un cast que
    le natif REFUSE : ni erreur ni crash, la behaviour se serait executee integralement. C'est le
    trou exact qu'un entrainement irait exploiter, et il est invisible en self-play."""
    _, atype, _, _, _, _ = next(c for c in CAS if c[0] == cas_id)
    n = gate181["native"][cas_id]
    avant = _port(gate181, _sans_masque(atype), n["caster_id"], n["target_id"])
    assert avant == 0, (
        "%s : sans `TARGETING_OPTIONS` le port devrait tout ACCEPTER (0) -- il rend %#x. Le gate "
        "vient donc d'ailleurs que du masque, et ce fichier ne prouve plus rien." % (cas_id, avant))


@pytest.mark.parametrize("cas_id", IDS)
def test_avec_masque_le_moteur_refuse_pour_la_meme_raison(gate181, cas_id):
    """Le masque pose par #181 rend le verdict offline EGAL au verdict natif -- ou 0 quand la regle
    native n'est pas portee par la cascade (cas `HEALABLE_1002`, degradation permissive assumee).

    Jamais un refus pour une AUTRE raison : c'est la signature d'un masque FAUX, et un test purement
    booleen accepte/refuse la laisserait passer."""
    _, atype, _, _, nat_attendu, port_attendu = next(c for c in CAS if c[0] == cas_id)
    n = gate181["native"][cas_id]
    apres = _port(gate181, ABILITY_CLASSES[atype](), n["caster_id"], n["target_id"])
    assert apres == int(port_attendu), (
        "%s : le port rend %#x, attendu %#x (natif %s %#x)"
        % (cas_id, apres, int(port_attendu), n["target_names"], n["target_hex"]))
    if port_attendu:
        assert apres == n["target_hex"], (
            "%s : refus pour une raison DIFFERENTE du natif -- port %#x, natif %s %#x"
            % (cas_id, apres, n["target_names"], n["target_hex"]))


def test_le_port_ne_refuse_jamais_ce_que_le_natif_accepte(gate181):
    """Propriete « zero regression » du contrat §3, sur TOUS les couples (caster du lot x unite
    vivante) : une regle non portee est permissive, donc un masque juste ne peut pas produire de
    refus la ou le natif accepte. C'est le sens qui casse en premier quand un masque porte un bit
    de trop."""
    bad = []
    for (atype, cu, uid), (nat, names) in gate181["broad"].items():
        if nat != 0:
            continue
        port = _port(gate181, ABILITY_CLASSES[atype](), cu, uid)
        if port != 0:
            bad.append((atype, cu, uid, hex(port)))
    assert not bad, ("le port refuse des cibles que le natif ACCEPTE "
                     "(ability, caster, cible, raison portee) : %s" % bad)


def test_aucun_refus_pour_la_mauvaise_raison(gate181):
    """Contrat §3 dans son autre sens, sur les MEMES couples : quand le natif refuse, le port rend
    soit EXACTEMENT sa raison, soit 0. Une troisieme valeur = masque faux."""
    wrong, exact = [], []
    for (atype, cu, uid), (nat, names) in gate181["broad"].items():
        if nat == 0:
            continue
        port = _port(gate181, ABILITY_CLASSES[atype](), cu, uid)
        if port == nat:
            exact.append((atype, uid, hex(nat), names))
        elif port != 0:
            wrong.append((atype, cu, uid, hex(port), hex(nat), names))
    assert not wrong, ("refus pour une raison DIFFERENTE du natif "
                       "(ability, caster, cible, port, natif, noms) : %s" % wrong)
    assert exact, "aucun refus natif reproduit a l'identique : test non discriminant"
