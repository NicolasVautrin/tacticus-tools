"""#953-r2 -- LA PLACE de `On(PreAttack = 5)` DANS LE VECTEUR ATTAQUE NORMALE, confrontee au natif.

CE QUE CE FICHIER GARDE
-----------------------
Sur une attaque NORMALE ranged, le natif applique le `+extraDmg` de `TerrifyingCrescendo_ExtraDmg`
(1424) au niveau qu'avait l'effet **AVANT** l'attaque -- alors que le port, depuis #512-r1,
appliquait niveau+1 : `SuppressiveFire` pose `Pinned` sur `On(PreAttack)`, ce qui monte le stack
d'un cran, et l'emission etait placee AU-DESSUS d'`attacker_modifiers`, donc les coups de l'attaque
DECLENCHANTE le voyaient. Mesure (`probe_953r2_ecart_ranged_shiron.py`, `MC1_67` / 777,
`emperNoiseMarine` << Shiron >>, TROIS attaques successives, meme etat et meme flux RNG) :

    passe | niveau 1424 AVANT (natif) | NATIF | PORT avant #953-r2
      0   |            -              | 4699  | 6396   (+36 %)
      1   |            1              | 6301  | 8541   (+35 %)
      2   |            2              | 8230  | 10526  (+28 %)

CE QUI SEPARE CE VECTEUR DE CELUI DES ABILITIES, LU AU DECOMPILE (pas deduit de l'ecart) :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteNormalAttack` --
la base de TOUTE attaque normale -- termine par
`IdunBattle.Entities.Abilities.AActiveAbility$$ExecuteAtomic(behaviour, entities, 0x3d)`, donc par
`IdunBattleLogic.Entities.DSLBehaviors$$AtomicGroup` ; et
`IdunBattle.Operations.AtomicGroupOperation$$Execute` porte une FILE, depilee APRES la cloture du
groupe (slots 20/21 d'`IBattleQuery` puis slot 10, rejoue par `IOperationProcessor.EvaluateAbilities`
slot 78 / `UnregisterEntityFromTriggers` slot 85). `1197 ExcruciatingFrequencies`, elle, passe par
`Execute` et NON `ExecuteAtomic` (case-512 §1) : ses triggers sont immediats, et
`probe_512 --regime R1` reste VERT bit-exact avec la place remontee sur la voie ABILITY.

LES CINQ CRANS
--------------
  1. **GEOMETRIE** -- calculee puis ASSERTIONNEE contre le `boardGraph` LIVE (le montage reprend le
     bras TEMOIN `oa_away` de #953/#954 : le porteur d'aura est ADJACENT A L'ATTAQUANT, pas a la
     victime, donc aucune aura ne mord et le seul canal qui reste est celui de Shiron).
  2. **EGALITE A L'UNITE, COUP PAR COUP**, sur DEUX passes successives. La passe 1 est le vrai
     discriminant : le niveau du stack y est deja NON NUL avant l'attaque, donc un port qui
     appliquerait << le niveau d'apres >> et un port qui appliquerait << zero >> divergent tous les
     deux, dans des sens opposes.
  3. **LE TRIGGER N'EST PAS MORT** -- le stack MONTE bien a chaque passe (`None -> 1 -> 2`). Sans ce
     cran, retirer purement le trigger rendrait ce fichier VERT : le vert du correctif et le vert
     d'une neutralisation seraient indistinguables.
  4. **CONTRE-EPREUVE PAR MUTATION** -- le rejeu MUTANT rejoue `On(5)` AVANT l'attaque, ce qui
     reconstitue exactement la place d'avant #953-r2. Il doit DIVERGER du natif sur les deux
     passes. Mesure : il rend `6396` et `8541`, c'est-a-dire l'ANCIEN port A L'UNITE -- la mutation
     mord, et elle mord juste.
  5. **TEMOIN MELEE** -- meme attaquant, meme cible, arme de melee : le gate `IsRangedAttack` de
     `SuppressiveFireAbility$$CreateTrigger` ferme, le stack NE monte PAS, et le port egale le natif.
     Si une correction de la place bougeait le regime melee, elle serait fausse.

Montage et mesure : `scripts/python/probe_953r2_ecart_ranged_shiron.py`.
ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LA PLACE GARDEE, et le vecteur qu'elle deplace
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # LES DEUX CONSOMMATEURS PORTES de `On(PreAttack = 5)`
        "scripts/python/engine/runner/operations/triggers/loki/suppressive_fire.py",
        "scripts/python/engine/runner/operations/triggers/loki/let_the_galaxy_burn.py",
        # LA CASCADE : la pose d'effet, l'evenement qu'elle emet, et le trigger qui l'ecoute
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/operations/triggers/loki/terrifying_crescendo.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/phase.py",
        # LE CANAL DEGAT que le stack alimente, et l'agregateur qui le lit
        "scripts/python/engine/entities/effects/loki/extra_damage.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/runner/damage_model.py",
        # LE PIPELINE de degat traverse par le rejeu offline
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/damage_hits.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/runner.py",
        "scripts/python/engine/runner/prng.py",
        "scripts/python/engine/entities/pathfinding/board.py",
        # LE MONTAGE : ce probe, celui dont il emprunte la geometrie, le pilote de runner
        "scripts/python/probe_953r2_ecart_ranged_shiron.py",
        "scripts/python/probe_953_954_skullsmasher_obsessive_annunciation.py",
        "scripts/python/probe_r6_round_materialize.py",
        "scripts/python/rl_duel.py",
        "scripts/python/hexgeo.py",
        "scripts/python/board.py",
        # LES MAGNITUDES (relues du gameconfig a chaque appel) et LA GEOMETRIE du board
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/gameconfig.py",
        # (`data/symbols/**` est ajoute par `declencheur_cliquet` DU FAIT de `build: True` --
        #  ecrire le hash ici le figerait au build du jour, cf. #431 / #962)
        "data/boards/pvp/MC1_67.json",
        "data/boards/global/MC1_67.json",
        "data/seed-bc.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "La PLACE de `On(PreAttack = 5)` dans le vecteur attaque normale, les deux "
              "consommateurs portes de ce vecteur, la cascade pose-d'effet -> `PreEffectAdded` -> "
              "`TerrifyingCrescendo`, le canal degat que le stack alimente, le pipeline que le "
              "rejeu offline traverse, le montage live, et les ENTREES qui fixent magnitudes et "
              "geometrie. `build: True` : le montage confronte un runner NATIF -- un changement de "
              "build change les deux cotes.",
}

import pytest                                                              # noqa: E402

import probe_953r2_ecart_ranged_shiron as P                                # noqa: E402

#: DEUX passes suffisent a rendre le discriminant : la passe 0 part d'un stack ABSENT, la passe 1
#: d'un stack DEJA POSE. Une troisieme n'ajoute aucun regime (mesuree, elle concorde aussi).
PASSES = 2


@pytest.fixture(scope="module")
def bras(live_session):
    """Les deux bras. Portee MODULE : tous les tests partagent la mesure (deux runners au total)."""
    ranged = P.run(place_remontee=True, repeats=PASSES, verbose=True)
    if ranged.get("error"):
        pytest.fail("montage #953-r2 (ranged) NON INSTALLE : %s" % ranged["error"], pytrace=False)
    melee = P.run(melee=True, repeats=1, verbose=True)
    if melee.get("error"):
        pytest.fail("montage #953-r2 (melee) NON INSTALLE : %s" % melee["error"], pytrace=False)
    return ranged, melee


def test_geometrie_est_celle_demandee(bras):
    """(1) La geometrie EST le discriminant : elle est ASSERTIONNEE contre le `boardGraph` LIVE."""
    ranged, melee = bras
    for nom, r in (("ranged", ranged), ("melee", melee)):
        g = r.get("geo") or {}
        assert not g.get("fail"), "geometrie #953-r2 (%s) : %s" % (nom, g.get("fail"))
        assert g.get("d_ada_att") == 1, (
            "%s : le porteur d'aura doit etre ADJACENT A L'ATTAQUANT (bras TEMOIN d'aura) -- d=%s"
            % (nom, g.get("d_ada_att")))
        assert (g.get("d_ada_victim") or 0) >= 2, (
            "%s : le porteur d'aura doit etre HORS CONTACT de la victime, sinon son aura mord et "
            "le canal mesure n'est plus celui de Shiron -- d=%s" % (nom, g.get("d_ada_victim")))
    assert (ranged["geo"].get("d_att_victim") or 0) >= 2, (
        "ranged : l'attaquant doit tirer A DISTANCE (d=%s)" % ranged["geo"].get("d_att_victim"))
    assert melee["geo"].get("d_att_victim") == 1, (
        "melee : l'attaquant doit etre AU CONTACT (d=%s)" % melee["geo"].get("d_att_victim"))


def test_port_egale_natif_a_l_unite_sur_deux_passes(bras):
    """(2) Le rejeu OFFLINE egale le natif A L'UNITE, coup par coup, sur les deux passes.

    La passe 1 est le vrai discriminant : le stack y est deja NON NUL avant l'attaque."""
    ranged, _ = bras
    passes = ranged.get("passes") or []
    assert len(passes) == PASSES, "il manque des passes : %d" % len(passes)
    for p in passes:
        n, port = p["native"], p["port"]
        assert n["n"] > 0, (
            "passe %d : le natif n'a rendu AUCUN coup -- montage a REFUSER, pas a interpreter"
            % p["passe"])
        assert list(port["per_hit"]) == list(n["hits"]), (
            "passe %d : port %s != natif %s" % (p["passe"], port["per_hit"], n["hits"]))
        assert port["total"] == n["total"], (
            "passe %d : total port %s != natif %s" % (p["passe"], port["total"], n["total"]))


def test_le_stack_monte_vraiment(bras):
    """(3) Le trigger n'est PAS mort : le stack monte d'un cran a CHAQUE passe, des DEUX cotes.

    Sans ce cran, retirer le trigger rendrait le fichier VERT -- le vert du correctif et celui
    d'une neutralisation seraient indistinguables."""
    ranged, _ = bras
    passes = ranged.get("passes") or []
    for p in passes:
        av = p["port"]["crescendo_level_before"] or 0
        ap = p["port"]["crescendo_level_after"] or 0
        assert ap == av + 1, (
            "passe %d : le stack PORTE n'a pas monte d'un cran (%s -> %s) -- le trigger est mort"
            % (p["passe"], p["port"]["crescendo_level_before"],
               p["port"]["crescendo_level_after"]))
        noms_apres = [e[2] for e in (p["att_effects_after"] or [])]
        assert "TerrifyingCrescendo_ExtraDmg" in noms_apres, (
            "passe %d : le NATIF ne porte pas 1424 apres l'attaque (%s) -- le montage n'exerce pas "
            "la cascade" % (p["passe"], p["att_effects_after"]))
    #: Le niveau NATIF d'avant la passe 1 est celui d'apres la passe 0 : c'est ce chainage qui
    #: rend la passe 1 discriminante (un stack DEJA pose, contre un stack absent en passe 0).
    if len(passes) >= 2:
        niv = {e[0]: e[1] for e in (passes[1]["att_effects_before"] or [])}
        assert niv.get(1424) == 1, (
            "la passe 1 doit partir d'un stack DEJA POSE au niveau 1 (natif : %s)"
            % passes[1]["att_effects_before"])


def test_la_place_remontee_diverge(bras):
    """(4) CONTRE-EPREUVE. Le rejeu MUTANT rejoue `On(5)` AVANT l'attaque -- exactement la place
    d'avant #953-r2. Il DOIT diverger du natif sur les deux passes.

    Un mutant VERT serait le resultat SUSPECT (mutation qui ne mord pas), pas une bonne nouvelle."""
    ranged, _ = bras
    for p in (ranged.get("passes") or []):
        mut, n = p.get("mutant"), p["native"]
        assert mut is not None, "passe %d : la contre-epreuve n'a pas ete jouee" % p["passe"]
        assert mut["total"] != n["total"], (
            "passe %d : la place REMONTEE rend le MEME total que le natif (%s) -- la mutation ne "
            "mord pas, le vert du test principal ne prouve donc rien" % (p["passe"], mut["total"]))
        assert mut["total"] > n["total"], (
            "passe %d : la place remontee doit SUR-estimer (elle fait voir niveau+1), or %s < %s"
            % (p["passe"], mut["total"], n["total"]))


def test_temoin_melee_ne_bouge_pas(bras):
    """(5) TEMOIN. Meme attaquant, meme cible, arme de MELEE : le gate `IsRangedAttack` du trigger
    ferme, le stack ne monte pas, et le port egale le natif. Une correction de la place qui
    bougerait ce regime serait fausse."""
    _, melee = bras
    passes = melee.get("passes") or []
    assert passes, "le bras melee n'a rendu aucune passe"
    p = passes[0]
    n, port = p["native"], p["port"]
    assert n["n"] > 0, "melee : le natif n'a rendu AUCUN coup -- montage a REFUSER"
    assert list(port["per_hit"]) == list(n["hits"]), (
        "melee : port %s != natif %s" % (port["per_hit"], n["hits"]))
    noms_apres = [e[2] for e in (p["att_effects_after"] or [])]
    assert "TerrifyingCrescendo_ExtraDmg" not in noms_apres, (
        "melee : le stack a monte alors que le gate `IsRangedAttack` doit le fermer (%s)"
        % (p["att_effects_after"],))
    assert p["port"]["crescendo_level_after"] == p["port"]["crescendo_level_before"], (
        "melee : le stack PORTE a monte (%s -> %s)"
        % (p["port"]["crescendo_level_before"], p["port"]["crescendo_level_after"]))
