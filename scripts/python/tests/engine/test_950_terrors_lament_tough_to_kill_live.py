"""#950 -- `TerrorsLament` (`eldarJainZar`) et `ToughToKill` (`astraDreir`), CONFRONTES AU NATIF.

CE QUE CE FICHIER GARDE -- cinq bras, une seule loi : **le rejeu OFFLINE egale le natif A L'UNITE,
coup par coup**. Rien n'est fitte ; la geometrie est CALCULEE et ASSERTIONNEE avant tout verdict
d'aval (quatre tuiles `Grass` a la MEME elevation sur `MC1_67`, cf. `probe_950`).

  1. **GEOMETRIE** -- l'attaquant est en `(0,1)`, au contact de sa cible, et Jain Zar est soit
     ADJACENTE a l'attaquant `(0,2)` soit a TROIS hex `(0,4)`. Dans le bras `aura` elle est a
     DEUX hex de la VICTIME : un port qui lirait l'adjacence a la CIBLE au lieu de l'adjacence a
     l'ATTAQUANT rendrait ce bras identique au temoin.
  2. **POSE** -- le porteur PORTE ses effets (1119+1120, ou 1472). Sans ce cran, un zero de canal ne
     se distinguerait pas d'un zero de pose.
  3. **LE NATIF DIT BIEN CA** -- `tl_aura` contre `tl_away` : **-1 coup** (`hitsReduction`) et un
     degat par coup STRICTEMENT plus bas (mesure : 6 coups / 9090 -> 5 coups / 3750, soit -797 =
     `dmgReduction[50] x 180 %` sur CHACUN des cinq coups restants). `ttk` contre `ttk_ctl` : le
     coup MAX tombe de 2540 a 1789 (les deux canaux CRIT).
  4. **LE PORT REPRODUIT** -- egalite A L'UNITE dans les CINQ bras.
  5. **LA REGEN** -- `ToughToKill_HealAbility` : +2659 PV au debut du tour de Dreir cote natif, et
     le port rend la MEME valeur par le MEME vecteur (`On(0x13 = TurnStart_Other)`).
  6. **CONTRE-EPREUVE** -- registre NEUTRALISE (c'est-a-dire l'etat d'`origin/master`), le rejeu
     DOIT diverger dans les bras porteurs et rester EGAL dans les temoins. Le premier verdict
     verifie que les deux bras ont la MEME mesure NATIVE : sans lui l'A/B ne serait pas attribuable,
     et un bras mutant VERT serait le resultat suspect (mutation qui ne mord pas), pas une preuve.

⚠ CE FICHIER GARDE AUSSI UN CORRECTIF DE FOYER PARTAGE. `AttackDamageOperation._crit_params`
evaluait `CouldCrit` sur les valeurs POST-BONUS : une reduction de crit-DEGAT assez grande pour
rendre `cd <= 0` y supprimait le TIRAGE, donc desynchronisait le flux PRNG de toute l'attaque. Le
natif, lui, lit `CouldCrit(attacker) = GetStat(9) > 0 && GetStat(10) > 0` (STATS BRUTES) et clampe
separement `CalculateCriticalDamage = Math.Max(0, GetStat(10) + Sigma)`. Le bras `ttk` est le SEUL
regime porte qui l'atteigne (`critDmgReduction[50] x 160 % = 1330` contre `GetStat(10) = 700`) --
c'est donc lui, et lui seul, qui empeche la regression.

Montage, mesure et verdicts : `scripts/python/probe_950_terrors_lament_tough_to_kill.py`. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LES DEUX PORTS TESTES
        "scripts/python/engine/entities/effects/loki/terrors_lament.py",
        "scripts/python/engine/entities/effects/loki/tough_to_kill.py",
        "scripts/python/engine/runner/operations/triggers/loki/tough_to_kill.py",
        # LES REGISTRES qui les rendent vivants (et que la contre-epreuve NEUTRALISE)
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # LES QUATRE CANAUX traverses, et les agregateurs qui les alimentent
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/services/attack_hits_formula.py",
        "scripts/python/engine/services/damage_modifiers.py",
        "scripts/python/engine/services/effect_bonus.py",
        # LE CONTEXTE : les deux facades qui posent `att_pos`/`owner_pos`/`att_traits`/`is_melee`
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/playbook/prediction/normal_attack.py",
        # LE FOYER CRIT PARTAGE -- ce fichier garde le correctif `CouldCrit`/clamp `cd` (#950)
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/services/damage_combat.py",
        # LE VECTEUR de la regen et l'Operation qu'il appelle
        "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/phase.py",
        "scripts/python/engine/runner/operations/heal.py",
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        # LE PIPELINE de degat traverse par le rejeu offline
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/damage_hits.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/runner.py",
        "scripts/python/engine/runner/prng.py",
        "scripts/python/engine/entities/pathfinding/board.py",
        # LE MONTAGE : le probe, le pilote de runner, la geometrie hex
        "scripts/python/probe_950_terrors_lament_tough_to_kill.py",
        "scripts/python/probe_r6_round_materialize.py",
        "scripts/python/rl_duel.py",
        "scripts/python/hexgeo.py",
        # LES MAGNITUDES : elles sont RELUES du gameconfig a chaque appel
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/gameconfig.py",
        # (`data/symbols/**` est ajoute par `declencheur_cliquet` DU FAIT de `build: True` --
        #  ecrire le hash ici le figerait au build du jour, cf. #431 / #962)
        # LA GEOMETRIE du board choisi
        "data/boards/global/MC1_67.json",
        "data/boards/pvp/MC1_67.json",
        "data/seed-bc.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Les deux ports, leurs registres, les QUATRE canaux d'effet traverses (degat "
              "defenseur SELF et AURA, coups defenseur SELF et AURA), le foyer CRIT partage dont "
              "ce fichier garde le correctif `CouldCrit`, le vecteur de regen, le pipeline de "
              "degat que le rejeu offline traverse, le montage live, et les ENTREES qui fixent "
              "les magnitudes (gameconfig) et la geometrie (board). `build: True` : le montage "
              "confronte un runner NATIF -- un changement de build du jeu change les deux cotes.",
}

import pytest                                                           # noqa: E402

import probe_950_terrors_lament_tough_to_kill as P                      # noqa: E402


def _run(arm, mutate=False):
    r = P.run(arm, mutate=mutate, verbose=True)
    if "error" in r:
        pytest.fail("montage #950 NON INSTALLE (%s%s) : %s"
                    % (arm, " mutant" if mutate else "", r["error"]), pytrace=False)
    return r


@pytest.fixture(scope="module")
def arms(live_session):
    """Les CINQ bras + leurs mutants. Portee MODULE : tous les tests partagent la mesure."""
    base = {a: _run(a) for a in ("tl_aura", "tl_away", "tl_self", "ttk", "ttk_ctl")}
    mut = {a: _run(a, mutate=True) for a in ("tl_aura", "tl_away", "ttk", "ttk_ctl")}
    return base, mut


def test_geometry_is_the_one_we_asked_for(arms):
    """(1) La geometrie EST le discriminant : si elle n'est pas celle demandee, tout verdict d'aval
    est vide."""
    base, _ = arms
    fails = [f for r in base.values() for f in P.verdict_geometry(r)]
    assert not fails, "geometrie #950 :\n  - " + "\n  - ".join(fails)


def test_carrier_actually_carries_its_effects(arms):
    """(2) Le porteur porte bien ses owner-effects -- sinon un zero de canal serait indistinguable
    d'un zero de pose."""
    base, _ = arms
    fails = [f for r in base.values() for f in P.verdict_carrier_effects(r)]
    assert not fails, "pose #950 :\n  - " + "\n  - ".join(fails)


def test_native_terrors_lament_discriminant(arms):
    """(3a) Le NATIF : Jain Zar adjacente a l'ATTAQUANT retire un coup et reduit le degat, a
    geometrie d'attaque identique."""
    base, _ = arms
    fails = P.verdict_terrors_lament(base["tl_aura"], base["tl_away"])
    assert not fails, "discriminant natif TerrorsLament :\n  - " + "\n  - ".join(fails)


def test_native_tough_to_kill_discriminant(arms):
    """(3b) Le NATIF : a `--crit 100,700`, la cible SANS `ToughToKill` encaisse strictement plus."""
    base, _ = arms
    fails = P.verdict_tough_to_kill(base["ttk"], base["ttk_ctl"])
    assert not fails, "discriminant natif ToughToKill :\n  - " + "\n  - ".join(fails)


@pytest.mark.parametrize("arm", ["tl_aura", "tl_away", "tl_self", "ttk", "ttk_ctl"])
def test_port_matches_native(arms, arm):
    """(4) Le PORT : rejeu offline sur le meme `State` et le meme flux RNG, egalite A L'UNITE."""
    base, _ = arms
    fails = P.verdict_port_matches_native(base[arm])
    assert not fails, "port vs natif #950 :\n  - " + "\n  - ".join(fails)


def test_regen_matches_native(arms):
    """(5) `ToughToKill_HealAbility` : meme montant, meme vecteur (`On(0x13 = TurnStart_Other`)."""
    base, _ = arms
    fails = P.verdict_regen(base["ttk"])
    assert not fails, "regen #950 :\n  - " + "\n  - ".join(fails)


@pytest.mark.parametrize("arm,porteur", [("tl_aura", True), ("tl_away", False),
                                         ("ttk", True), ("ttk_ctl", False)])
def test_registry_is_load_bearing(arms, arm, porteur):
    """(6) CONTRE-EPREUVE : registre neutralise -> divergence dans les bras porteurs, RIEN dans les
    temoins. Le premier verdict verifie que la mutation A MORDU."""
    base, mut = arms
    fails = P.verdict_mutation(base[arm], mut[arm], porteur)
    assert not fails, "discriminance #950 (%s) :\n  - %s" % (arm, "\n  - ".join(fails))


def test_regen_trigger_is_load_bearing(arms):
    """(6bis) La MEME contre-epreuve sur le vecteur de REGEN : `ABILITY_TRIGGERS["ToughToKill"]`
    retire, le port ne soigne plus rien la ou le natif soigne 2659."""
    base, mut = arms
    if mut["ttk"]["regen"]["port_delta"] == base["ttk"]["regen"]["native_delta"]:
        pytest.fail("[mutation] regen : le registre NEUTRALISE, le port soigne TOUJOURS %s -- la "
                    "mutation NE MORD PAS" % mut["ttk"]["regen"]["port_delta"], pytrace=False)
