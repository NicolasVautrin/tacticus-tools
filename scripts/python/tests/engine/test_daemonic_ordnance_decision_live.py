"""DaemonicOrdnance (1148) -- face DECISION a cible TUILE, confrontee au LIVE (case-302, tranche 3).

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident :

A. **La ROUTE a cibles TUILE existe et sert.** Le bras `noroute` (registre `NONATTACK_PLAYBOOKS`
   vide) rejoue la decision dans l'etat d'AVANT le port ; le bras `domaine UNITE force` coupe
   l'autre moitie (l'enumeration). Le bras `best_attack` verifie la troisieme porte : `_best_attack`
   consomme `ranked`, or 1148 cible une TUILE et n'y a aucune entree.
B. **Le terme custom est NECESSAIRE** : force a 0, le moteur DIVERGE (il retombe sur l'attaque
   normale, que le natif ne choisit pas dans ce regime).
C. **La cible emise est bien une ENTITE-TUILE** (id du `boardGraph`, pas de `decisionView.units`).
D. **La forme est LINEAIRE en n** : `10 x |ennemis sur GetTargetAreaTiles|`, plusieurs valeurs
   distinctes sur le domaine.
E. **Le montage n'est pas complaisant** : le bras TEMOIN (cibles one-shot, `KillUnit` domine)
   verifie que le natif NE caste PAS 1148 quand l'attaque normale vaut mieux -- et que le moteur le
   suit. Sans lui, un port qui casterait 1148 *toujours* passerait A/B/C/D.
F. **Le COOLDOWN est purge avant de conclure** (`initialCooldownTurns = 1`). Sans cette purge,
   « le natif ne propose pas 1148 » ne mesurerait que l'indisponibilite -- l'artefact qui avait
   produit une conclusion architecturale fausse sur 1169 (`case-302` §5).
G. **La DIRECTION du triangle suit le PLATEAU, et c'est mesure des DEUX cotes.**
   `DaemonicOrdnanceAbility$$GetTargetAreaTiles` = `TilesOnSameElevation(target,
   TilesInTriangleShape(target, If(IsPositionMachineForCurrentPlayer(2), 1, 4)), 1)`, et le
   predicat lit `BattleQuery$$GetPositionMachineForPlayer` = la `MachineOfWarPosition` du GROUPE DE
   SPAWN du joueur courant -- une propriete du plateau, PAS le slot d'une machine deployee. Deux
   bras :
     * `MC1_67` (`SpawnPointSetIndex 1`) declare `(TWPI 0 -> 2)` -> predicat VRAI -> `{S, SE}` ;
     * `C1_03` declare `(0, 0)` -> predicat FAUX -> `{NW, N}`.
   Le natif change de cible entre les deux ; le moteur doit changer AVEC lui. Le bras `nogroups`
   (canal coupe) DIVERGE sur `MC1_67` : c'est le ROUGE vu AVANT le correctif, conserve comme garde.

PORTEUR : 1148 est portee par `blackForgefiend` (MACHINE OF WAR, hors `decisionView.units`). Le
montage la GREFFE sur `deathTyphus` (Death Guard, DANS le pool rank 17) -- le natif charge le
playbook PAR ABILITY, jamais par unite (`case-92` §5bis), et le custom de 1148 ne lit NI stat NI
trait du caster (seulement `caster.team`, pour `IsEnemy`).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_302_3_daemonic_ordnance as AB                   # noqa: E402

DO = AB.DAEMONIC                                             # 1148
NORMAL = AB.NORMAL                                           # 69


@pytest.fixture(scope="module")
def arms():
    rids = []
    try:
        a = AB.measure(AB.HP_FAVOURABLE, "rs_302_3_t_a.json")      # 1148 domine
        rids.append(a["rid"])
        b = AB.measure(AB.HP_WITNESS, "rs_302_3_t_b.json")         # TEMOIN : l'attaque domine
        rids.append(b["rid"])
        f = AB.measure(AB.HP_FAVOURABLE, "rs_302_3_t_f.json", AB.BOARD_FLAT)   # groupe a MoWPos 0
        rids.append(f["rid"])
        yield {"do": a, "temoin": b, "flip": f}
    finally:
        for rid in rids:
            AB.dispose(rid)


def test_cooldown_is_purged_before_measuring(arms):
    """F : sans cette purge, « le natif ne propose pas 1148 » ne mesure que l'indisponibilite."""
    for k, r in arms.items():
        assert r["cooldown"] in (None, 0), (
            "bras %s : 1148 encore en cooldown (%s) -- la mesure ne dit rien du ciblage"
            % (k, r["cooldown"]))


def test_ability_is_in_the_real_kit_with_a_tile_domain(arms):
    """L'ability est vue par `unitAbilityTypes` (pas seulement par un `abilityTargets` force) et son
    domaine est ENTIEREMENT tuile -- le bit `TargetIsTile` du masque `0x46000040`."""
    for k, r in arms.items():
        s = r["stage"]
        assert s["in_kit"] and s["usable"], "bras %s : 1148 absente/inutilisable du kit reel" % k
        assert s["target_count"] > 10, "bras %s : domaine 1148 minuscule (%s)" % (k, s["target_count"])
        assert set(s["target_kinds"]) == {"tile"}, (
            "bras %s : domaine non homogene %s -- `GetPossibleTargetsForOptions` appelle "
            "`GetTilesInRange` OU `GetUnitsInRange`, jamais les deux" % (k, s["target_kinds"]))


def test_engine_matches_native_on_all_arms(arms):
    """Le moteur reproduit le choix NATIF (ability ET cible) dans les trois bras."""
    for k, r in arms.items():
        assert r["engine"]["on"] == r["native"], (
            "bras %s : moteur %s != natif %s" % (k, r["engine"]["on"], r["native"]))


def test_native_casts_the_ordnance_only_in_the_favourable_arm(arms):
    """E : le montage SEPARE bien les deux regimes -- sinon il ne mesure rien."""
    assert arms["do"]["native"][0] == DO, (
        "le natif ne caste pas 1148 dans le regime favorable -- le montage ne mord plus")
    assert arms["temoin"]["native"][0] != DO, (
        "le natif caste 1148 MEME dans le regime temoin -- l'accord du bras favorable ne prouve rien")


def test_tile_route_is_necessary(arms):
    """A : sans la route non-attaque, le moteur ne PEUT PAS proposer 1148."""
    for k in ("do", "flip"):
        e = arms[k]["engine"]
        assert e["on"][0] == DO
        assert e["noroute"][0] != DO, (
            "bras %s : le moteur propose 1148 SANS la route -- une autre voie la fait passer" % k)


def test_best_attack_can_never_yield_the_ordnance(arms):
    """A (2e porte) : `_best_attack` rend l'attaque normale, jamais 1148."""
    for k, r in arms.items():
        assert r["engine"]["best_attack_ability"] != DO, (
            "bras %s : `_best_attack` a rendu 1148" % k)


def test_custom_term_is_necessary(arms):
    """B : force a 0, le custom fait DIVERGER le moteur du natif au bras favorable."""
    for k in ("do", "flip"):
        e = arms[k]["engine"]
        assert e["zero"] != e["on"], (
            "bras %s : custom force a 0 ne change rien -> le terme est inerte" % k)


def test_target_is_a_tile_entity(arms):
    """C : la cible retenue est un id de TUILE (boardGraph), pas un id d'unite."""
    for k in ("do", "flip"):
        r = arms[k]
        tid = r["engine"]["on"][1]
        assert tid in r["engine"]["targets"], (
            "bras %s : la cible %s hors de l'ensemble eligible TUILE %s"
            % (k, tid, r["engine"]["targets"][:8]))
        assert tid != r["caster"]


def test_unit_domain_is_empty_which_is_exactly_the_state_before_the_fix(arms):
    """VUE ROUGE, MESUREE : avec le domaine force a UNITE (le code d'avant la route tuile),
    `eligible_targets` rend un ensemble VIDE -> l'action 1148 n'existe pas cote moteur."""
    for k, r in arms.items():
        assert r["engine"]["targets_unit_domain"] == [], (
            "bras %s : le domaine UNITE rend %s -- 1148 aurait donc eu une route AVANT la tranche"
            % (k, r["engine"]["targets_unit_domain"][:8]))


def test_custom_is_linear_not_boolean(arms):
    """D : le custom prend plusieurs valeurs distinctes, toutes multiples de 10 (`Fix64(0xa)`)."""
    for k in ("do", "flip"):
        vals = sorted({c for _t, c in arms[k]["engine"]["per_target"]})
        assert len(vals) > 2, (
            "bras %s : le custom ne prend que %s valeur(s) -- selecteur mort ou montage sans "
            "contraste" % (k, vals))
        assert all(abs(v % AB.ENEMY_STEP) < 1e-9 for v in vals), (
            "bras %s : %s ne sont pas des multiples de %s -- la forme n'est pas `n x 10`"
            % (k, vals, AB.ENEMY_STEP))


def test_prediction_term_is_zero_because_the_area_is_not_burning(arms):
    """RESIDU NOMME (tranche 2) rendu VISIBLE : `MakeDamagePredictions` boucle sur
    `GetAllDamageableTargets` = les ennemis sur une tuile DEJA EN FEU. La zone ne brule pas encore
    (c'est ce meme cast qui pose le feu, en DERNIER etage de son behaviour), donc la somme des
    predictions vaut REELLEMENT 0 et le port est exact dans ce regime. Le jour ou la tranche 2
    porte le terme, ce test DOIT tomber -- c'est son role."""
    for k, r in arms.items():
        nz = [t for t, n in (r["engine"]["pred_counts"] or {}).items() if n]
        assert not nz, (
            "bras %s : %d cible(s) rendent des predictions non vides -- le regime a change, "
            "le terme de prediction n'est plus nul par construction" % (k, len(nz)))


def test_spawn_group_channel_drives_the_triangle_direction(arms):
    """G : la `MachineOfWarPosition` lue est celle du GROUPE DE SPAWN du plateau, et elle CHANGE le
    resultat observable.

    `MC1_67`/set 1 declare `(TWPI 0 -> 2)` : predicat VRAI, triangle `{S, SE}`, et le cluster
    `(A, A+S, A+SE)` donne un custom MAXIMAL de 30 (les trois ennemis sur une seule zone).
    `C1_03` declare `(0, 0)` : predicat FAUX, triangle `{NW, N}`, maximum 20."""
    do, flip = arms["do"], arms["flip"]
    assert do["engine"]["mow_position"] == 2, (
        "MC1_67 devrait donner MachineOfWarPosition = 2, mesure %s" % do["engine"]["mow_position"])
    assert flip["engine"]["mow_position"] == 0, (
        "C1_03 devrait donner MachineOfWarPosition = 0, mesure %s" % flip["engine"]["mow_position"])
    assert max(c for _t, c in do["engine"]["per_target"]) == 3 * AB.ENEMY_STEP, (
        "triangle {S,SE} attendu sur MC1_67 : le custom maximal devrait etre 30")
    assert max(c for _t, c in flip["engine"]["per_target"]) == 2 * AB.ENEMY_STEP, (
        "triangle {NW,N} attendu sur C1_03 : le custom maximal devrait etre 20")


def test_cutting_the_spawn_group_channel_makes_the_engine_diverge(arms):
    """G (le ROUGE) : le bras `nogroups` rejoue la MEME decision sans le canal
    `SpawnPointGroups`. Sur `MC1_67` le predicat retombe alors sur son repli (aucune MoW deployee
    -> inconnu -> False), le triangle bascule sur `{NW, N}` et le moteur vise une AUTRE tuile.

    C'est la mesure de l'etat d'AVANT le correctif -- pas une hypothese sur lui. Si ce test cessait
    de mordre, c'est que l'accord de `test_engine_matches_native_on_all_arms` viendrait d'ailleurs
    que de la lecture du groupe de spawn."""
    do = arms["do"]["engine"]
    assert do["nogroups"] != do["on"], (
        "canal SpawnPointGroups coupe : le moteur rend %s, identique au bras cable -- la lecture "
        "du groupe n'est donc pas ce qui produit l'accord" % (do["nogroups"],))
    assert do["nogroups"][0] == DO, (
        "sans le canal, le moteur devrait quand meme caster 1148 (seule la CIBLE change) ; il rend "
        "%s -- le bras ne mesure plus la direction du triangle" % (do["nogroups"],))
