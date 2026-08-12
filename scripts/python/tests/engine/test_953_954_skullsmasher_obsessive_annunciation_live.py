"""#953 / #954 -- `Skullsmasher` (`worldJakhal`) et `ObsessiveAnnunciation` (`emperKakophonist`),
CONFRONTES AU NATIF.

CE QUE CE FICHIER GARDE -- huit bras, une seule loi : **le rejeu OFFLINE egale le natif A L'UNITE,
coup par coup**. Rien n'est fitte ; la geometrie est CALCULEE (solveur sur le dump de board :
elevation CONSTANTE, LOS, tuiles non-`Block`) puis ASSERTIONNEE contre le `boardGraph` LIVE avant
tout verdict d'aval.

  1. **GEOMETRIE** -- Adamatar est soit ADJACENT A LA VICTIME (bras), soit ADJACENT A L'ATTAQUANT et
     a >= 2 hex de la victime (TEMOIN). C'est ce second cran qui rend le temoin DISCRIMINANT : un
     port qui lirait l'adjacence a l'ATTAQUANT au lieu de l'adjacence a la VICTIME rendrait
     `oa_away` identique a `oa_aura`.
  2. **POSE** -- le porteur PORTE ses effets. Pour `Skullsmasher` ce cran garde le SEED
     (`ABILITY_INIT_OWNER_EFFECTS`) : la `CreateActiveCondition` de 1263 est
     `AmountIsGreaterThanZero(GetMissingHealthSteps())`, donc a PV PLEINS l'effet est INACTIF et le
     canal ACTIF-ONLY ne le publie PAS -- sans le seed, le port n'a AUCUNE instance a rallumer.
  3. **LE NATIF DIT BIEN CA** -- `oa_aura` contre `oa_away` : +974 sur le coup, soit
     `extraDmg[L50] x 160 %` (mesure `MC1_67`/777 : 5338 contre 4364 ; `C4_09`/31337 : 6339 contre
     5365 -- MEME ecart, deux boards). `sk_hurt` contre `sk_full` : +1000 par coup a 5 paliers de
     PV manquants, soit `extraDmg[L50] x 180 % = 200` par palier.
  4. **LE PORT REPRODUIT** -- egalite A L'UNITE dans les huit bras.
  5. **LE STUN** -- `sk_stun` : la cible ressort avec `Stunned` (1162 + ses trois enfants), et Macer
     avec le marqueur permanent `Skullsmasher_StunEffect` (1264) ; `sk_nostun`, meme montage et
     meme passage de tour SANS le kill, ne les a pas.
  6. **CONTRE-EPREUVE** -- port NEUTRALISE (l'etat d'`origin/master`), le rejeu DOIT diverger dans
     les bras porteurs et rester EGAL dans les temoins. Le premier verdict verifie que les deux
     runs ont la MEME mesure NATIVE : sans lui l'A/B ne serait pas attribuable, et un bras mutant
     VERT serait le resultat SUSPECT (mutation qui ne mord pas), pas une preuve.
  7. **CONTRE-EPREUVE SELECTIVE** -- la face CRIT est falsifiee SEULE (`--mutate-effect
     ObsessiveAnnunciation_ExtraCritDmg`) : sans cela son ecart serait MELANGE a celui de la face
     DEGAT, qui s'applique au meme coup. Et le meme geste sur `oa_crit_nonchaos` ne change RIEN :
     c'est la preuve que le conjoint `HasTrait(Caster, Chaos)` MORD.

⚠ CE FICHIER GARDE AUSSI UN CORRECTIF DE FOYER PARTAGE. `melee_defeats` (compteur de
`BlessingsOfKhorne`) n'etait pose que par la face DECISION : sur un etat RECHARGE, le `+3 % x N`
que ce trait verse sur TOUT le degat sortant d'un World Eater DISPARAISSAIT des le premier kill de
melee. Le bras `sk_stun` est le SEUL regime porte qui l'atteigne (Macer tue en melee AVANT la
mesure) -- c'est donc lui, et lui seul, qui empeche la regression. MESURE avant correctif : natif
`[1210, 1204, 503]` = 2917, port `[791, 607, 1089]` = 2487.

Montage, mesure et verdicts : `scripts/python/probe_953_954_skullsmasher_obsessive_annunciation.py`.
ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LES DEUX PORTS TESTES
        "scripts/python/engine/entities/effects/loki/skullsmasher.py",
        "scripts/python/engine/entities/effects/loki/obsessive_annunciation.py",
        "scripts/python/engine/runner/operations/triggers/loki/skullsmasher.py",
        "scripts/python/engine/runner/operations/triggers/loki/obsessive_annunciation.py",
        # LES REGISTRES qui les rendent vivants (et que la contre-epreuve NEUTRALISE)
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # LES CANAUX traverses, et les agregateurs qui les alimentent
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/services/damage_modifiers.py",
        "scripts/python/engine/services/effect_bonus.py",
        # LE SELECTEUR d'aura et son evaluation par-porteur
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/runner/components.py",
        # LE CONTEXTE : les facades qui posent `owner_health` et `adjacent_enemy_ids_of`
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/playbook/prediction/normal_attack.py",
        "scripts/python/engine/playbook/prediction/abilities.py",
        # LE VECTEUR des deux triggers (mort, attaque) et l'Operation qu'ils appellent
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/phase.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        # LE PIPELINE de degat traverse par le rejeu offline
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/damage_hits.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/runner.py",
        "scripts/python/engine/runner/prng.py",
        "scripts/python/engine/entities/pathfinding/board.py",
        # LE MONTAGE : le probe, le pilote de runner, la geometrie hex, le lecteur de board
        "scripts/python/probe_953_954_skullsmasher_obsessive_annunciation.py",
        "scripts/python/probe_r6_round_materialize.py",
        "scripts/python/rl_duel.py",
        "scripts/python/hexgeo.py",
        "scripts/python/board.py",
        # LES MAGNITUDES : elles sont RELUES du gameconfig a chaque appel
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/gameconfig.py",
        # (`data/symbols/**` est ajoute par `declencheur_cliquet` DU FAIT de `build: True` --
        #  ecrire le hash ici le figerait au build du jour, cf. #431 / #962)
        # LA GEOMETRIE du board choisi
        "data/boards/pvp/MC1_67.json",
        "data/boards/global/MC1_67.json",
        "data/seed-bc.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Les deux ports, leurs registres, les canaux d'effet traverses (degat AURA cote "
              "defenseur, crit-degat AURA, degat SELF attaquant), le foyer PARTAGE `melee_defeats` "
              "dont ce fichier garde le correctif, les DEUX vecteurs de trigger (mort et attaque), "
              "le pipeline de degat que le rejeu offline traverse, le montage live, et les ENTREES "
              "qui fixent les magnitudes (gameconfig) et la geometrie (board). `build: True` : le "
              "montage confronte un runner NATIF -- un changement de build change les deux cotes.",
}

import pytest                                                              # noqa: E402

import probe_953_954_skullsmasher_obsessive_annunciation as P              # noqa: E402


def _run(arm, mutate=False, mutate_effect=None):
    r = P.run(arm, mutate=mutate, mutate_effect=mutate_effect, verbose=True)
    if r.get("error"):
        pytest.fail("montage #953/#954 NON INSTALLE (%s%s) : %s"
                    % (arm, " mutant" if mutate else "", r["error"]), pytrace=False)
    return r


@pytest.fixture(scope="module")
def arms(live_session):
    """Les huit bras + leurs mutants. Portee MODULE : tous les tests partagent la mesure."""
    base = {a: _run(a) for a in ("oa_aura", "oa_away", "oa_melee", "oa_crit", "oa_crit_nonchaos",
                                 "sk_full", "sk_hurt", "sk_stun", "sk_nostun")}
    mut = {a: _run(a, mutate=True) for a in ("oa_aura", "oa_away", "oa_melee",
                                             "sk_hurt", "sk_full")}
    sel = {a: _run(a, mutate_effect=["ObsessiveAnnunciation_ExtraCritDmg"])
           for a in ("oa_crit", "oa_crit_nonchaos")}
    return base, mut, sel


def test_geometry_is_the_one_we_asked_for(arms):
    """(1) La geometrie EST le discriminant : si elle n'est pas celle demandee, tout verdict d'aval
    est vide. Elle est ASSERTIONNEE contre le `boardGraph` LIVE, pas supposee."""
    base, _, _ = arms
    fails = [f for r in base.values() for f in P.verdict_geometry(r)]
    assert not fails, "geometrie #953/#954 :\n  - " + "\n  - ".join(fails)


def test_carrier_actually_carries_its_effects(arms):
    """(2) Le porteur porte bien ses effets -- sinon un zero de canal serait indistinguable d'un
    zero de POSE. Ce cran garde AUSSI le seed `ABILITY_INIT_OWNER_EFFECTS["Skullsmasher"]`, sans
    lequel un Macer a PV pleins n'a aucune instance de 1263 a rallumer."""
    base, _, _ = arms
    fails = [f for r in base.values() for f in P.verdict_carrier_effects(r)]
    assert not fails, "pose #953/#954 :\n  - " + "\n  - ".join(fails)


def test_native_aura_discriminant(arms):
    """(3) Le NATIF : a geometrie d'attaque IDENTIQUE, Adamatar ADJACENT A LA VICTIME fait encaisser
    strictement plus que le meme Adamatar adjacent a l'ATTAQUANT."""
    base, _, _ = arms
    fails = P.verdict_aura_discriminant(base["oa_aura"], base["oa_away"])
    assert not fails, "discriminant natif ObsessiveAnnunciation :\n  - " + "\n  - ".join(fails)


def test_native_missing_health_discriminant(arms):
    """(3bis) Le NATIF : Macer BLESSE frappe strictement plus fort que Macer a PV pleins."""
    base, _, _ = arms
    hurt = (base["sk_hurt"].get("native") or {}).get("total")
    full = (base["sk_full"].get("native") or {}).get("total")
    assert hurt and full and hurt > full, (
        "[natif] Skullsmasher ne discrimine PAS : sk_hurt=%s <= sk_full=%s -- le bras BLESSE n'a "
        "franchi aucun palier de `hpPct`, la mesure serait un second temoin" % (hurt, full))


@pytest.mark.parametrize("arm", ["oa_aura", "oa_away", "oa_melee", "oa_crit", "oa_crit_nonchaos",
                                 "sk_full", "sk_hurt", "sk_stun", "sk_nostun"])
def test_port_matches_native(arms, arm):
    """(4) Le PORT : rejeu offline sur le meme `State` et le meme flux RNG, egalite A L'UNITE."""
    base, _, _ = arms
    fails = P.verdict_port_matches_native(base[arm])
    assert not fails, "port vs natif #953/#954 :\n  - " + "\n  - ".join(fails)


def test_stun_is_posed_and_only_after_a_kill(arms):
    """(5) `Skullsmasher_TriggerStunAbility` : la cible ressort `Stunned` SI et SEULEMENT SI Macer
    a deja tue, et le port rend la MEME liste d'effets."""
    base, _, _ = arms
    fails = P.verdict_stun(base["sk_stun"], base["sk_nostun"])
    assert not fails, "stun #953 :\n  - " + "\n  - ".join(fails)


@pytest.mark.parametrize("arm,porteur", [("oa_aura", True), ("oa_away", False),
                                         ("oa_melee", False), ("sk_hurt", True),
                                         ("sk_full", False)])
def test_registry_is_load_bearing(arms, arm, porteur):
    """(6) CONTRE-EPREUVE : port neutralise -> divergence dans les bras porteurs, RIEN dans les
    temoins. Le premier verdict verifie que les deux runs ont la MEME mesure NATIVE."""
    base, mut, _ = arms
    fails = P.verdict_mutation(base[arm], mut[arm], porteur)
    assert not fails, "discriminance #953/#954 (%s) :\n  - %s" % (arm, "\n  - ".join(fails))


def test_crit_face_is_load_bearing_and_gated_on_chaos(arms):
    """(7) CONTRE-EPREUVE SELECTIVE de la face CRIT, et du conjoint qui la garde.

    Neutraliser le SEUL `ObsessiveAnnunciation_ExtraCritDmg` doit faire DIVERGER `oa_crit`
    (attaquant CHAOS) et ne RIEN changer a `oa_crit_nonchaos` (attaquant Imperial) : c'est la preuve
    que le conjoint `HasTrait(Caster@+0x48, 0x7ea = Chaos)` MORD, et qu'il n'a pas ete recopie
    depuis la moitie DEGAT (qui, elle, porte `IsRangedAttack` et PAS ce gate)."""
    base, _, sel = arms
    fails = P.verdict_mutation(base["oa_crit"], sel["oa_crit"], True)
    fails += P.verdict_mutation(base["oa_crit_nonchaos"], sel["oa_crit_nonchaos"], False)
    assert not fails, "face CRIT #954 :\n  - " + "\n  - ".join(fails)
