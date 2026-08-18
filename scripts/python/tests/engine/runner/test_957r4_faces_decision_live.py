"""#957-r4 -- GARDE des DEUX confrontations LIVE laissees ouvertes par #957.

Les deux volets etaient PORTES et gardes OFFLINE, et AUCUN n'avait ete confronte au natif : les
trois montages de #957 portaient `darkaAsmodai` / `spaceRockfist` / `tyranDeathleaper`, jamais
`astraBullgryn` (1017) ni `genesPrimus` (1179) -- les deux pourtant dans `rl_duel build --list-pool`.

Les deux oracles sont DIFFERENTS, et c'est la STRUCTURE du playbook natif qui l'impose :

  * `IdunBattle.AI.Playbook.Loki.FragBombPlaybook` surcharge `MakeDamagePredictions` -> oracle
    DIRECT `aiPlaybookPredict` (il invoque cette methode et rend ses `ProbableDamageEvent`) ;
  * `IdunBattle.AI.Playbook.Loki.CultDemagoguePlaybook` surcharge `EvaluateInternal` et n'a AUCUNE
    `MakeDamagePredictions` -- le corps generique de `ComparablePlaybook<T>` LEVE. Ni
    `aiPlaybookPredict` ni `pairUtility` ne rendent donc son utilite : l'oracle est le TOUR D'IA
    OBSERVE (`aiDryRunAllUnits`), c'est-a-dire la CIBLE que le natif choisit.

Trois montages, trois fixtures NOMMEES de portee module. Mesure et recherche de geometrie :
`probe_957r4_faces_decision_live.py` (ce fichier n'en est que le cran).

⚠ DEUX PIEGES DE HARNAIS, tous deux MESURES par ce probe et tous deux silencieux :
  * `aiDryRunAllUnits` porte ses messages sous `proposed`, PAS sous `action.messages`. Lire la
    mauvaise clef rend `None`, qui se lirait comme << le natif ne propose pas 1179 >> -- un REGIME
    NON ARME qui n'existe pas.
  * un `applyAction` de type `move` vers une tuile OCCUPEE echoue EN SILENCE. Un << echange >> de
    deux unites pose sans degager d'abord est donc un NO-OP integral, et les etiquettes imprimees
    mentent. Le montage PARQUE tout le monde loin avant de placer.

ASCII only.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_130_placement_sort_rng as P130  # noqa: E402
import probe_957r4_faces_decision_live as P  # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/entities/abilities/active_ability.py",
                "scripts/python/engine/playbook/prediction/abilities.py",
                "scripts/python/engine/playbook/bespoke.py",
                "scripts/python/probe_957r4_faces_decision_live.py",
                "scripts/python/tests/engine/runner/test_957r4_faces_decision_live.py"),
    "build": True,
    "toujours": False,
    "raison": "Il garde l'ACCORD avec le natif du volet SPLASH de la prediction de 1017 et de "
              "l'ancre du terme dominant de 1179 -- les deux confrontations que #957 avait "
              "laissees ouvertes.",
}

_HP = ["--hp-target", "120000", "--hp-player", "120000", "--no-ai"]


def _monte(p_units, a_units, seed, corps):
    """Monte un runner ISOLE, joue `corps(rpc, rid)`, dispose. Un montage KO n'est JAMAIS un
    verdict sur le port : il fait `pytest.fail` en le disant."""
    rpc = P130.Rpc()
    sf = P.ROOT / "logs" / "runners" / ("t957r4-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = P._build(sf, p_units, a_units, _HP, seed=seed)
    if rid is None:
        pytest.fail("montage impossible : `rl_duel build` a echoue (ce n'est PAS un verdict sur le "
                    "port -- reparer le montage)")
    try:
        return corps(rpc, rid)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sf).unlink(missing_ok=True)


# ============================================================================================
#  1017 FragBomb -- le volet SPLASH de la PREDICTION
# ============================================================================================

@pytest.fixture(scope="module", name="splash_entoure")
def _splash_entoure():
    """Cible au centre d'un anneau de 6 voisins marchables, caster dans l'anneau, ALLIE dans le
    voisinage de la cible (fixture `_ringed_cast.ring_scenario`, deja livree par la face COMBAT)."""
    res = _monte("%s,%s" % (P.BULL, P.ALLY_1017), P.ENEMIES_1017, "777",
                 lambda rpc, rid: P.confronte_fragbomb(rpc, rid, isole=False))
    assert res.get("ok"), "confrontation impossible : %s" % res.get("raison")
    return res


@pytest.fixture(scope="module", name="splash_isole")
def _splash_isole():
    """CONTRE-CAS : tout le monde a >=4 hex de la cible -- l'anneau est VIDE."""
    res = _monte("%s,%s" % (P.BULL, P.ALLY_1017), P.ENEMIES_1017, "31337",
                 lambda rpc, rid: P.confronte_fragbomb(rpc, rid, isole=True))
    assert res.get("ok"), "confrontation impossible : %s" % res.get("raison")
    return res


def test_le_regime_du_splash_est_ARME(splash_entoure):
    """TEMOIN NON NUL, joue AVANT le verdict : sans voisinage, le volet splash ne s'exerce pas et
    l'accord des tests suivants ne prouverait rien de plus que la cible principale."""
    assert splash_entoure["ring"], (
        "anneau VIDE : la geometrie n'a pas arme le volet splash -- reparer le montage, "
        "ne pas lire l'accord qui suit comme une confirmation")
    assert int(splash_entoure["ally"]) in [int(x) for x in splash_entoure["ring"]], (
        "l'ALLIE n'est pas dans le voisinage de la cible : le friendly-fire n'est pas exerce")
    assert splash_entoure["nrOfHits"] != splash_entoure["nrOfHits2"], (
        "regime DEGENERE : nrOfHits == nrOfHits_2, les deux batchs ne se distinguent pas")


def test_le_natif_predit_cible_ET_voisinage(splash_entoure):
    """`...FragBombPlaybook$$MakeDamagePredictions` emet DEUX batchs : la cible principale, puis un
    batch `DSLSelectors$$Entity(e)` par entite de `...FragBombAbility$$GetAdjacentTargets`."""
    obtenu = {int(e["target"]) for e in splash_entoure["events"] if e["target"] is not None}
    attendu = {int(splash_entoure["target"])} | {int(u) for u in splash_entoure["ring"]}
    assert obtenu == attendu, (
        "le natif predit %s ; cible+voisinage = %s" % (sorted(obtenu), sorted(attendu)))
    assert int(splash_entoure["caster"]) not in obtenu, (
        "le CASTER est predit -- le set natif le SOUSTRAIT (`op_Subtraction <DSLSelectors+0x48>`)")


def test_les_coups_par_batch_sont_ceux_du_port(splash_entoure):
    """Le port surcharge DEUX `hits` (`_frag_bomb_inputs`) : `nrOfHits` sur le batch principal,
    `nrOfHits_2` sur le batch splash. Le natif doit appliquer exactement ceux-la."""
    port = P._port_fragbomb(splash_entoure)
    par_cible = {}
    for e in splash_entoure["events"]:
        par_cible.setdefault(int(e["target"]), set()).add(e["hits"])
    principal = par_cible.pop(int(splash_entoure["target"]))
    assert principal == {port["hits_principal"]}, (
        "cible principale : natif %s coups != port %s" % (principal, port["hits_principal"]))
    for tid, hits in sorted(par_cible.items()):
        assert hits == {port["hits_splash"]}, (
            "splash u%s : natif %s coups != port %s" % (tid, hits, port["hits_splash"]))


def test_le_friendly_fire_est_DANS_la_face_decision(splash_entoure):
    """`...FragBombAbility$$GetAdjacentTargets` n'a AUCUN wrapper `Enemies` (contraste
    `MassDriverAcceleratorAbility$$GetAdjacentAttackTargets`, qui en a un) : l'ALLIE adjacent a la
    tuile ciblee est PREDIT, et son evenement est `friendly` -- utilite NEGEE. La face COMBAT le
    mesurait deja ; la face DECISION ne l'avait jamais mesure."""
    obtenu = {int(e["target"]) for e in splash_entoure["events"] if e["target"] is not None}
    assert int(splash_entoure["ally"]) in obtenu, (
        "l'allie u%s n'est PAS predit : le set aurait un filtre d'equipe" % splash_entoure["ally"])


def _par_cible(events):
    out = {}
    for e in events:
        if e["target"] is not None:
            out.setdefault(int(e["target"]), set()).add(e["hits"])
    return out


def test_le_port_rend_LES_MEMES_evenements(splash_entoure):
    """LE cran MORDANT cote port : `engine.playbook.prediction.abilities.make_damage_predictions`
    -- le chemin qui consomme `FragBombAbility.get_aoe_targets` ET `_frag_bomb_inputs` -- doit rendre
    exactement les memes (cible, coups) que le natif sur CE meme etat. Les tests precedents
    confrontent le natif a la GEOMETRIE du montage ; celui-ci le confronte au PORT."""
    port = splash_entoure.get("port_events")
    assert port, ("evenements du port NON MESURES (predicteur offline indisponible) -- "
                  "reparer le montage, ne pas lire l'accord des autres tests comme une preuve "
                  "que le port est d'accord")
    assert _par_cible(port) == _par_cible(splash_entoure["events"]), (
        "port %s != natif %s" % (sorted(_par_cible(port).items()),
                                 sorted(_par_cible(splash_entoure["events"]).items())))


def test_cible_isolee_aucun_splash(splash_isole):
    """CONTRE-CAS : le volet splash n'est pas un forfait -- sans voisin, un SEUL evenement."""
    par_cible = {}
    for e in splash_isole["events"]:
        par_cible.setdefault(int(e["target"]), set()).add(e["hits"])
    port = P._port_fragbomb(splash_isole)
    assert par_cible == {int(splash_isole["target"]): {port["hits_principal"]}}, (
        "cible isolee : le natif predit %s, attendu le seul batch principal a %s coups"
        % (sorted(par_cible.items()), port["hits_principal"]))


# ============================================================================================
#  1179 CultDemagogue -- l'ANCRE du terme dominant
# ============================================================================================

@pytest.fixture(scope="module", name="ancre_1179")
def _ancre_1179():
    """Cherche un montage ou l'ancre CIBLE et l'ancre CASTER designent des cibles DIFFERENTES.

    Il faut DEUX conditions simultanees : un ecart de tuiles libres sous le plafond `nrOfSummons`,
    ET que la cible PAUVRE soit la PREMIERE enumeree (l'ancre CASTER retombe sur la premiere au tie,
    son terme 1 etant constant sur les cibles et le terme 2 nul)."""
    res = _monte("%s,%s" % (P.PRIMUS, P.ALLIES_1179), P.ENEMIES_1179, "777",
                 lambda rpc, rid: P.confronte_cultdemagogue(rpc, rid, rpc.sid))
    assert res.get("ok"), "confrontation impossible : %s" % res.get("raison")
    return res


def test_le_regime_de_l_ancre_est_ARME(ancre_1179):
    """TEMOIN NON NUL, joue AVANT le verdict. Sans ces trois crans l'accord suivant serait obtenu en
    regime DEGENERE et ne prouverait rien : (a) les deux termes 1 PLAFONNES doivent differer ;
    (b) la cible PAUVRE doit etre enumeree la premiere ; (c) les deux ancres doivent effectivement
    designer des cibles DIFFERENTES."""
    g = ancre_1179["geo"]
    assert g["ecart"] >= 1, (
        "les deux termes 1 coincident une fois plafonnes a nrOfSummons=%s (libres %s vs %s) : "
        "l'ancre ne peut pas departager" % (ancre_1179["plafond"], g["libres_pauvre"],
                                            g["libres_riche"]))
    assert g["ordre"] and int(g["ordre"][0]) == int(g["pauvre"]), (
        "la cible PAUVRE n'est pas la premiere enumeree (%s) : l'ancre CASTER designerait la MEME "
        "cible que l'ancre CIBLE" % (g["ordre"],))
    pc, pk = ancre_1179["port_cible"], ancre_1179["port_caster"]
    assert pc.get("target") != pk.get("target"), (
        "regime DEGENERE : les deux ancres designent u%s toutes les deux" % pc.get("target"))


def test_le_natif_ancre_le_terme_dominant_sur_la_CIBLE(ancre_1179):
    """LA question binaire de #957 §5. `...CultDemagogueAbility$$PossibleTilesForDecoys` =
    `CanAddUnit(SurroundingTiles(<DSLSelectors+0x60>, ...))`, et `<DSLSelectors+0x60>` est `Target`.
    Le port comptait les tuiles libres autour du CASTER : le terme dominant etait alors CONSTANT sur
    les cibles et ne departageait plus l'argmax."""
    nat, pc, pk = ancre_1179["natif"], ancre_1179["port_cible"], ancre_1179["port_caster"]
    assert nat is not None and int(nat.get("ability") or 0) == P.ABILITY_1179, (
        "le natif ne propose pas 1179 pour ce caster (%s) -- rien a confronter sur l'ancre" % (nat,))
    assert pc.get("ability") == P.ABILITY_1179, (
        "le port ne propose pas 1179 (%s) -- l'ancre n'est pas en cause"
        % ({k: pc.get(k) for k in ("kind", "ability", "target")}))
    assert int(nat["target"]) == int(pc["target"]), (
        "le natif cible u%s ; ancre CIBLE -> u%s ; ancre CASTER -> u%s"
        % (nat["target"], pc.get("target"), pk.get("target")))
