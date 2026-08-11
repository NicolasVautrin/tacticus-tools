"""#926 -- GARDE LIVE du passif `FirstAmongTraitors` (`blackAbaddon`), les TROIS faces.

Le probe `probe_926_first_among_traitors.py` MESURE ; ce fichier ASSERTE. Il rejoue ses etages sur
UN runner (montage a positions FORCEES, board `MC1_67`, seed 777) et exige :

  [2] l'effet-AURA 1063 est porte par ABADDON SEUL (owner-effect pose a l'init de l'ability) ;
  [3] PREDICTION -- accord avec l'oracle NATIF `decisionView...ranked[].dmg{Min,Max}` sur CHAQUE
      tuile candidate, ET le montage doit couvrir des tuiles DEDANS et DEHORS du rayon (sinon le
      gate geometrique n'est pas exerce et l'accord ne prouve rien) ;
  [4] DECISION -- accord avec le total NATIF de `TriggeredAbilitiesUtility` par (unite, tuile),
      capte par `triggeredMoveTrace` (armement NOMINATIF par `runnerId`, il ne touche pas les
      mesures des autres agents). `check_value` de #443-r1a porte ses TROIS gardes contre l'accord
      degenere (>= 1 ligne, >= 1 valeur native non nulle, >= 2 valeurs natives distinctes) ;
  [5] le TERME CROISSANT -- Abaddon attaque, `TotalAttacksMade` avance, la prediction NATIVE des
      beneficiaires MONTE, et le port suit ;
  [6] COMBAT -- `attacker_modifiers().additive` porte la valeur EXACTE sur le seul beneficiaire,
      et 0 sur les trois unites que le selecteur natif ecarte ;
  [7] MUTANTS -- quatre mutations du port doivent TOUTES faire rougir [6]. Un mutant vert dit que
      le temoin est aveugle.

⚠ Ce qui n'est PAS mesure ici, et pourquoi : la prediction CONTRE la cible qu'Abaddon vient de
frapper. Son attaque normale declenche `LetTheGalaxyBurn`, qui pose l'effet de tuile
`DespoiledGround` (1476) sous elle ; le volet `DespoiledGround_ExtraDamagePct` (1478) n'est PAS
porte (residu ANTERIEUR, `docs/rl/case-159-rng-canal179-et-maybe-ltgb.md`), d'ou un ecart x1.25 a
x1.33 etranger a ce cas. L'etage 5 mesure donc sur l'AUTRE ennemi.

Un seul runner pour tout le fichier (`scope="module"`), dispose au teardown. ASCII only."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

#: #486-r15 -- les chemins dont une modification DOIT rejouer ce fichier. Perimetre pris LARGE :
#: l'accord depend de TOUTE la chaine (le probe qui porte montage et mesure, la classe d'effet et
#: sa magnitude, les deux registres, la feuille de decision et son dispatcher, le compteur
#: `ActorStatisticsComponent+0x20` et son seeding, et les DEUX foyers d'agregation d'aura).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/probe_926_first_among_traitors.py",
        "scripts/python/probe_443r1a_triggered_move_anchor.py",
        "scripts/python/engine/entities/effects/loki/first_among_traitors.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/playbook/friends_in_range.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/playbook/non_owner.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/utilities/tile.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Live : monte DEUX runners a positions FORCEES et confronte les TROIS faces du "
              "passif a leurs oracles NATIFS -- prediction par tuile candidate "
              "(`decisionView...ranked[]`), terme de decision par (unite, tuile) "
              "(`triggeredMoveTrace`), et canal COMBAT (`attacker_modifiers.additive`). Quatre "
              "mutants doivent mordre. Toute modification du port, d'un registre, du compteur "
              "`TotalAttacksMade` ou d'un foyer d'agregation peut deplacer l'accord.",
}

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_926_first_among_traitors as P                        # noqa: E402


@pytest.fixture(scope="module")
def runner926(tmp_path_factory):
    state = tmp_path_factory.mktemp("st926") / "st-926-live.json"
    P.STATE = state
    rid = P.build(state)
    dec = P.rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    scene, _sc = P._scene(rid, dec)
    by_vis = P.ids_by_visual(dec)
    mult = scene.mult(by_vis[P.CARRIER]) or 100
    lvl = scene.ablvl_by_id.get(by_vis[P.CARRIER]) or 50
    bonus = P.attendu_bonus(rid, dec, lvl, mult)      # FIGE avant toute mutation (etage 7)
    yield {"rid": rid, "dec": dec, "lvl": lvl, "mult": mult, "bonus": bonus, "by_vis": by_vis}
    P._duel(["dispose", "--state-file", str(state)])


def test_effet_1063_porte_par_abaddon_seul(runner926):
    """`AOwnerEffectTriggeredAbility$$CreateBehaviour` = `AddEffect(0x427, ..., source = Owner,
    targets = Owner)` -> l'effet-ENTITE vit sur le porteur ; ce sont ses CIBLES qui rayonnent."""
    rows = P.etage2(runner926["dec"])["rows"]
    assert rows[P.CARRIER]["porte_1063"], "Abaddon ne porte pas l'owner-effect 1063"
    for vis in (P.NEAR_CHAOS, P.PLAIN, P.FAR_CHAOS, P.FOE_NEAR, P.FOE_FAR):
        assert not rows[vis]["porte_1063"], \
            "%s porte 1063 : ce n'est PAS un effet projete sur les cibles" % vis
    # Le montage DOIT etre discriminant : un ami Chaos dedans, un Imperial dedans, un Chaos dehors.
    assert rows[P.NEAR_CHAOS]["dist"] is not None and rows[P.NEAR_CHAOS]["dist"] <= 2
    assert rows[P.PLAIN]["dist"] is not None and rows[P.PLAIN]["dist"] <= 2
    assert rows[P.FAR_CHAOS]["dist"] is not None and rows[P.FAR_CHAOS]["dist"] > 2


def test_prediction_accord_avec_l_oracle_natif_par_tuile(runner926):
    """Oracle NON circulaire : `decisionView.attackPlans[].evals[].ranked[].dmg{Min,Max}` du NATIF,
    par tuile candidate, confronte a `prediction.make_normal_attack_predictions` du port."""
    r = P.etage3(runner926["rid"], runner926["dec"])
    assert r["rows"], "aucune tuile candidate rankee -- le montage ne mesure RIEN"
    # Le gate GEOMETRIQUE doit etre EXERCE : sans tuile hors rayon, un port sans gate passerait.
    toutes = sorted({d for ds in r["distances"].values() for d in ds if d is not None})
    assert any(d <= 2 for d in toutes) and any(d > 2 for d in toutes), \
        ("le montage ne couvre pas a la fois l'interieur et l'exterieur du rayon 2 "
         "(distances vues : %s) -- l'accord ne prouverait pas le gate" % toutes)
    assert not r["bad"], "ECART(S) prediction natif/port :\n  " + "\n  ".join(r["bad"][:10])


def test_decision_accord_sur_le_terme_triggered_abilities(runner926):
    """`triggeredMoveTrace` : total natif de la feuille `TriggeredAbilitiesUtility` par
    (unite, tuile) vs la feuille portee. `check_value` (#443-r1a) refuse l'accord degenere."""
    r = P.etage4(runner926["rid"])
    if r.get("status") == "no-sensor":
        pytest.skip("capteur `triggeredMoveTrace` absent de la session (exige un reinject) -- "
                    "la face DECISION n'est PAS confrontee ici, et rien n'en est conclu")
    assert r["status"] == "ok", r["message"]


def test_combat_valeur_exacte_et_zero_sur_les_ecartes(runner926):
    """Canal COMBAT (`damage_model.attacker_modifiers`) : le DELTA imputable a 1063 (mesure en
    retirant la classe du registre) doit valoir la magnitude EXACTE sur le seul beneficiaire, et
    0 sur le porteur, sur l'ami non-Chaos et sur l'ami hors rayon."""
    d = runner926
    r = P.etage6(d["rid"], d["dec"], d["lvl"], d["mult"], bonus=d["bonus"])
    assert d["bonus"] > 0, "regime DEGENERE : magnitude nulle, ce test ne prouverait rien"
    assert r["ok"], "\n".join(
        "%-17s delta=%s attendu=%s" % (v, x["delta_1063"], x["attendu"])
        for v, x in r["rows"].items())


def test_mutants_mordent_tous(runner926):
    """Quatre mutations du port -- gate de trait, rayon, patte SELF, magnitude. Chacune DOIT faire
    rougir l'etage COMBAT. `bonus` est FIGE avant les mutations : recalcule, il se deplacerait avec
    la mutation de magnitude et la ferait passer pour verte."""
    d = runner926
    r = P.etage7(d["rid"], d["dec"], d["lvl"], d["mult"], d["bonus"])
    assert r["ok"], "mutant(s) VERT(S) -- le temoin est aveugle : %s" % (
        [k for k, v in r["mutants"].items() if v])


def test_terme_croissant_le_natif_monte_et_le_port_suit(runner926):
    """DERNIER de ce runner : il MUTE l'etat (Abaddon attaque). `TotalAttacksMade` (+0x20) avance
    -> la prediction NATIVE du beneficiaire contre l'ennemi NON frappe monte, et le port suit."""
    d = runner926
    r = P.etage5(d["rid"], d["dec"])
    if r.get("montage") == "KO":
        pytest.fail("MONTAGE KO -- l'attaque d'Abaddon n'a pas eu lieu ; rien n'est mesure")
    assert r["monte"], ("le NATIF n'a pas monte apres l'attaque (avant=%s apres=%s) : le terme "
                        "croissant n'est pas exerce, l'accord ne prouverait rien"
                        % (r["avant"], r["apres"]))
    assert not r["bad"], "ECART(S) apres l'attaque :\n  " + "\n  ".join(r["bad"][:10])


def test_un_ami_NON_CIBLABLE_recoit_quand_meme_le_bonus(tmp_path):
    """Le volet « Targetable » du `unitSelectionType = 3` -- et LE contre-exemple au voisin de forme.

    Sur le canal STAT-MOD, ce volet est REEL : mesure live de `LionHelm`, `darkaTerminator` en
    `TeleportStrike_TeleportingIn` ne recoit RIEN. Sur CE canal, la mesure dit l'INVERSE : le natif
    accorde le bonus a un ami Chaos non ciblable. Ce test grave le regime MESURE -- ajouter un gate
    `is_targetable` a `create_aura_attack_damage_bonus_for_ally` serait un ecart RESTRICTIF, et il
    ne rougirait dans aucun autre test.

    Second runner (le roster change), dispose par le probe."""
    r = P.etage8_deep_strike(tmp_path / "st-926-ds.json")
    assert r["exerce"], ("le beneficiaire ne porte PAS `TeleportStrike_TeleportingIn` : le regime "
                         "n'est pas exerce, ce test ne prouverait rien")
    assert r["bonus"] > 0, "regime DEGENERE : magnitude nulle"
    assert not r["bad"], "ECART(S) prediction natif/port :\n  " + "\n  ".join(r["bad"][:10])
    assert r["donne"] == r["bonus"], \
        ("le port accorde %s au lieu de %s a l'ami NON CIBLABLE, alors que l'oracle natif est en "
         "accord sur toutes les tuiles" % (r["donne"], r["bonus"]))
