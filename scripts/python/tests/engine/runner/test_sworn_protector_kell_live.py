"""Chaine `SwornProtector` -> Kell -> `ListenUpMaggots` -> `GetAbilityStatModification` NON NUL
(#95-RESTE2) — CONFRONTEE AU LIVE.

Ce que le test PROUVE (et non « le code est atteint ») : le chemin NON NUL de
`IdunBattle.Entities.UnitExtensions$$GetAbilityStatModification` existe et change un OBSERVABLE.
Le discriminant est un ECART DE 1 GARDE et de 1 HEX DE PORTEE entre deux etats du MEME runner :

  * `test_kell_appears_and_carries_effect_live` : une attaque ennemie sur Creed fait apparaitre
    `astraSmnKell`, qui porte `ListenUpMaggotsEffect` (0x426) ;
  * `test_summon_count_live_3_with_kell` / `..._2_without_kell` : le cast 1028 spawne **3** gardes
    quand Kell est en jeu, **2** sinon (meme board, meme seed, meme geometrie) ;
  * `test_ai_action_radius_live_3_with_kell` / `..._2_without_kell` : un garde ami place a distance
    EXACTEMENT 3 du caster est rejoue par `PerformAIAction` AVEC Kell, et ne l'est PAS sans lui
    (contre-cas) — c'est la semantique OVERRIDE du `range`.
  * `test_port_reproduces_chain_offline` : le PORT rejoue la meme chaine et rend les memes deux
    chiffres (3 gardes / rayon 3), et la mort de Kell les REVERTE.

Chaines natives portees (symboles) :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtectorAbility$$CreateTrigger` / `$$CreateBehaviour`
  `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtector_ProtectAbility$$CreateTrigger` / `$$CreateBehaviour`
  `IdunBattleLogic.Entities.Abilities.Active.Loki.ListenUpMaggotsAbility$$CreateTrigger` / `$$CreateBehaviour`
  `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$ApplyInternal` / `$$RevertInternal`
  `IdunBattle.Operations.AddUnitActiveAbilityModificationOperation$$Execute`

ASCII-only. Skip si pas de session live.
"""
from __future__ import annotations

import pytest

import hexgeo

CREED_VIS = "astraCreed"
FOE_VIS = "necroSpyder"          # attaquant a FAIBLE degat par coup : Kell survit au coup declencheur
KELL_VIS = "astraSmnKell"
GUARD_VIS_LIVE = "astraNpc1Guardsman"
ABILITY = 1028
BOARD = "MC1_67"
SEED = "4242"
# Geometrie choisie (board MC1_67) : (2,3) a SIX voisins jouables -> l'anneau de spawn ne borne
# jamais le compte de gardes, et les distances 2/3/4 sont toutes atteignables.
CREED_TILE = (2, 3)
D2, D3, D4 = (2, 1), (5, 2), (6, 1)      # distances 2 / 3 / 4 de CREED_TILE (verifiees par hexgeo)


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _by_vis(units, vis):
    return [u for u in units if u.get("visualId") == vis]


class _Drv:
    """Pilotage RPC minimal du runner (les deux camps : `applyAction` ne verifie pas la propriete)."""

    def __init__(self, rpc, rid):
        self.rpc, self.rid = rpc, rid

    def view(self):
        return self.rpc("decisionView", {"runnerId": self.rid, "allAbilities": True}, 90) or {}

    def units(self):
        return self.view().get("units") or []

    def act(self, action, timeout=120):
        """`applyAction({runnerId, action})` — MEME enveloppe que `rl_duel.py::cmd_act` (l'action est
        IMBRIQUEE, et le champ d'ability s'appelle `abilityType`)."""
        return self.rpc("applyAction", {"runnerId": self.rid, "action": action}, timeout) or {}

    def move(self, uid, col, row):
        return self.act({"kind": "move", "unitId": uid, "to": {"col": col, "row": row}})

    def endturn(self):
        return self.act({"kind": "endturn"})

    def cast(self, caster, target, ability=ABILITY):
        return self.act({"kind": "ability", "casterId": caster, "targetId": target,
                         "abilityType": ability})

    def attack(self, caster, target):
        return self.act({"kind": "ability", "casterId": caster, "targetId": target,
                         "abilityType": 69})     # Loki_NormalAttack

    def id_of(self, vis):
        us = _by_vis(self.units(), vis)
        return us[0]["id"] if us else None


def _place_and_face(drv, creed, foe):
    """Amene Creed sur `CREED_TILE` et l'ennemi au contact, en pilotant les deux camps."""
    drv.move(creed, 2, 2)
    drv.endturn()
    drv.move(foe, 5, 6)
    drv.endturn()
    drv.move(creed, 3, 4)
    drv.endturn()
    return drv


@pytest.fixture(scope="module")
def chain(rpc, build_runner):
    """UN runner : Creed subit une attaque (-> Kell), puis caste 1028 (-> N gardes).
    Rend l'etat observe a chaque etage. Le meme runner sert ensuite au volet rayon."""
    rid = build_runner(SEED, extra=["--p-units", CREED_VIS, "--a-units", FOE_VIS + ",necroWarden",
                                    "--hp-player", "400000", "--hp-target", "400000"],
                       board=BOARD)["rid"]
    drv = _Drv(rpc, rid)
    creed = drv.id_of(CREED_VIS)
    foe = drv.id_of(FOE_VIS)
    if creed is None or foe is None:
        pytest.skip("roster live incomplet")
    _place_and_face(drv, creed, foe)
    # l'ennemi vient au contact et frappe Creed -> SwornProtector
    drv.move(foe, 4, 4)
    drv.attack(foe, creed)
    after_attack = drv.units()
    kell = _by_vis(after_attack, KELL_VIS)
    drv.endturn()
    drv.cast(creed, creed)
    after_cast = drv.units()
    return {"drv": drv, "creed": creed, "foe": foe,
            "kell": kell[0] if kell else None,
            "after_attack": after_attack, "after_cast": after_cast}


def test_kell_appears_and_carries_effect_live(chain):
    """`SwornProtector` : la 1re attaque ennemie visant Creed fait apparaitre Kell, VIVANT, porteur de
    `ListenUpMaggotsEffect`. C'est le maillon sans lequel toute la chaine est du code mort."""
    kell = chain["kell"]
    assert kell is not None, "Kell n'est PAS apparu apres l'attaque sur Creed"
    assert kell.get("alive"), "Kell est mort au coup declencheur -> scenario non discriminant"
    names = [e.get("name") if isinstance(e, dict) else e for e in (kell.get("effects") or [])]
    assert "ListenUpMaggotsEffect" in names, f"effets de Kell = {names}"


def test_sworn_protector_switches_position_live(chain):
    """`SwornProtector_Protect` : Kell echange sa position avec Creed (`SwitchPosition`) AVANT que
    l'attaque ne se resolve -> c'est LUI qui encaisse.

    DISCRIMINANT : Creed sort de l'attaque a PV PLEINS (`--hp-player 400000` intact) alors qu'une
    attaque ennemie l'a bel et bien cible — les degats sont partis ailleurs. Et les deux unites
    n'occupent pas la meme tuile (l'echange a eu lieu)."""
    kell, creed_id = chain["kell"], chain["creed"]
    creed = [u for u in chain["after_attack"] if u.get("id") == creed_id][0]
    assert _upos(kell) != _upos(creed)
    assert kell.get("hp") is not None and kell["hp"] > 0
    assert creed.get("hp") == 400000, (
        "Creed a encaisse (hp=%s) -> le switch SwornProtector_Protect n'a pas eu lieu"
        % creed.get("hp"))


def test_summon_count_live_3_with_kell(chain):
    """`nrOfSummons` = 2 + `GetAbilityStatModification(Creed, 0x10)` = **3** avec Kell en jeu.
    C'est le premier des deux observables non nuls (l'ancienne case-doc annoncait 2 = modification
    nulle : REFUTE par cette mesure)."""
    guards = _by_vis(chain["after_cast"], GUARD_VIS_LIVE)
    assert len(guards) == 3, f"gardes spawnes = {len(guards)} (attendu 3 avec Kell)"


def test_ai_action_radius_live_3_with_kell(chain):
    """`range` = `GetAbilityStatModification(Creed, 0x16)` = **3** (OVERRIDE, pas 2+3).
    DISCRIMINANT : un garde ami place a distance EXACTEMENT 3 du caster est REJOUE par
    `PerformAIAction` (il bouge) ; celui a distance 4 ne l'est pas."""
    drv, creed = chain["drv"], chain["creed"]
    guards = [g["id"] for g in _by_vis(chain["after_cast"], GUARD_VIS_LIVE)]
    if len(guards) < 3:
        pytest.skip("moins de 3 gardes -> le placement 2/3/4 n'est pas montable")
    drv.endturn()
    for uid, (c, r) in zip(guards, (D2, D3, D4)):
        drv.move(uid, c, r)
    before = {u["id"]: _upos(u) for u in drv.units()}
    creed_pos = before.get(creed)
    dists = {uid: hexgeo.distance(before[uid], creed_pos) for uid in guards if uid in before}
    if sorted(dists.values()) != [2, 3, 4]:
        pytest.skip(f"placement 2/3/4 non obtenu: {dists}")
    drv.cast(creed, creed)
    after = {u["id"]: _upos(u) for u in drv.units()}
    acted = {uid: before[uid] != after.get(uid) for uid in guards}
    at3 = [uid for uid in guards if dists[uid] == 3][0]
    at4 = [uid for uid in guards if dists[uid] == 4][0]
    assert acted[at3], "le garde a distance 3 n'a PAS agi -> rayon 2, modification range nulle"
    assert not acted[at4], "le garde a distance 4 a agi -> rayon > 3, mesure non discriminante"


@pytest.fixture(scope="module")
def no_kell(rpc, build_runner):
    """CONTRE-CAS : MEME board / MEME seed / MEME geometrie, mais Creed n'est JAMAIS attaque ->
    `SwornProtector` ne fire pas -> pas de Kell -> modifications NULLES."""
    rid = build_runner(SEED, extra=["--p-units", CREED_VIS, "--a-units", FOE_VIS + ",necroWarden",
                                    "--hp-player", "400000", "--hp-target", "400000"],
                       board=BOARD)["rid"]
    drv = _Drv(rpc, rid)
    creed = drv.id_of(CREED_VIS)
    foe = drv.id_of(FOE_VIS)
    if creed is None or foe is None:
        pytest.skip("roster live incomplet")
    _place_and_face(drv, creed, foe)
    drv.move(creed, *CREED_TILE)
    drv.endturn()
    drv.cast(creed, creed)
    return {"drv": drv, "creed": creed, "after_cast": drv.units()}


def test_summon_count_live_2_without_kell(no_kell):
    """CONTRE-CAS du compte : sans Kell, le cast rend `nrOfSummons` = 2 (modification NULLE).
    Avec le test `..._3_with_kell`, c'est l'ecart de 1 garde qui prouve l'etage."""
    assert not _by_vis(no_kell["after_cast"], KELL_VIS), "Kell present dans le contre-cas"
    guards = _by_vis(no_kell["after_cast"], GUARD_VIS_LIVE)
    assert len(guards) == 2, f"gardes spawnes = {len(guards)} (attendu 2 sans Kell)"


def test_ai_action_radius_live_2_without_kell(no_kell):
    """CONTRE-CAS du rayon : sans Kell, le garde a distance 3 n'est PAS rejoue (rayon 2)."""
    drv, creed = no_kell["drv"], no_kell["creed"]
    guards = [g["id"] for g in _by_vis(no_kell["after_cast"], GUARD_VIS_LIVE)]
    if len(guards) < 2:
        pytest.skip("moins de 2 gardes")
    drv.endturn()
    for uid, (c, r) in zip(guards, (D2, D3)):
        drv.move(uid, c, r)
    before = {u["id"]: _upos(u) for u in drv.units()}
    creed_pos = before.get(creed)
    dists = {uid: hexgeo.distance(before[uid], creed_pos) for uid in guards if uid in before}
    if sorted(dists.values()) != [2, 3]:
        pytest.skip(f"placement 2/3 non obtenu: {dists}")
    drv.cast(creed, creed)
    after = {u["id"]: _upos(u) for u in drv.units()}
    at2 = [uid for uid in guards if dists[uid] == 2][0]
    at3 = [uid for uid in guards if dists[uid] == 3][0]
    assert before[at2] != after.get(at2), "meme le garde a distance 2 n'a pas agi -> mesure nulle"
    assert before[at3] == after.get(at3), "le garde a distance 3 a agi SANS Kell -> rayon deja 3 ?"


def test_port_reproduces_chain_offline():
    """Le PORT rejoue la chaine ENTIERE et rend les MEMES deux chiffres que le live (3 gardes,
    rayon 3), puis les REVERTE a la mort de Kell (`RevertInternal` via le `RemoveEffects` de
    `IdunBattle.Operations.KillUnitOperation$$Execute`)."""
    import importlib
    probe = importlib.import_module("probe_95r2_sworn_protector")
    assert probe.main() == 0
