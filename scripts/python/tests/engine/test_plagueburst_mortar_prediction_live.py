"""PlagueburstMortar (1169) -- terme de PREDICTION a cible TUILE, confronte au LIVE (case-302, tranche 2).

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident :

A. **L'ORACLE PAR ETAGE existe et est utilise.** `pairUtility(caster, <tileEntityId>, 1169)` invoque
   `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
   sur une cible TUILE -- exactement le terme que cette tranche porte (le CUSTOM n'y est pas). Si le
   bundle Frida injecte est anterieur au correctif hooks `#302-t5`, le RPC repond « target N not
   found » : le test ECHOUE en le disant, il ne skippe pas (un skip vert mentirait).
B. **Le port est bit-exact sur les CHAMPS de prediction** (`aiPlaybookPredict` vs
   `make_damage_predictions`) : min/max de degat sante, `appliedHits`, `hpBefore`.
C. **Le residu d'utilite est REFERME** (#333). `IdunBattle.Core.Services.MinMaxDamage$$Avg` =
   `(long)Fix64.Round((min+max)/2, midpointRounding = 0)` -- un arrondi DEMI-VERS-LE-PAIR --, que
   `engine.utilities.damage.DamageUtility` applique desormais aux DEUX termes (sante et bouclier).
   L'ecart port/natif est donc NUL sur toutes les tuiles (`+2.500e-03` -> `~8e-09` sur les sommes
   IMPAIRES, meme montage). Le test conserve son pouvoir discriminant par MUTATION : il rejoue le
   port d'AVANT #333 et exige que l'ecart REAPPARAISSE sur les sommes impaires.
D. **Le terme change la DECISION, et la mutation vire au ROUGE.** Bras DISCRIMINANT : le natif vise
   la tuile de l'ennemi du MILIEU (custom 20 + prediction) et non la tuile a 3 ennemis adjacents
   (custom 30, prediction 0). Vider `MakeDamagePredictions` fait basculer le moteur sur CETTE
   derniere -- meme ability, AUTRE tuile.
E. **Hors regime, le terme est un vrai no-op.** Bras TEMOIN (caster hors portee d'aura) : le predicat
   `GetIsValidAdjacentEnemyTrigger` est FAUX partout, tous les termes valent 0, et la mutation ne
   change RIEN -- la tranche 1 est preservee telle quelle.
F. **La PREDICTION ne couvre QUE l'occupant de la tuile visee.** `GetAdjacentDamageTargets` n'entre
   PAS dans `MakeDamagePredictions` : au plus UN event par tuile, et son `target` est l'occupant.
G. **Le COOLDOWN est purge avant de conclure** (meme lecon que la tranche 1).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_302_2_plagueburst_prediction as P              # noqa: E402
import probe_27_3_live as L                                 # noqa: E402

PB = P.PLAGUEBURST                                           # 1169


def _measure(caster_tile, state_name):
    rid = P.build(state_name, caster_tile)
    um = P._units(rid)
    cid = next(i for i, v in um.items() if v["vid"] == P.CASTER_VID)
    _cid, cooldown, _ = P._caster_state(rid)
    arm = P._arm(rid, state_name)
    arm.update({"rid": rid, "units": um, "cooldown": cooldown, "caster_pos": um[cid]["pos"]})
    return arm


@pytest.fixture(scope="module")
def arms():
    rids = []
    try:
        a = _measure(P.CENTER, "rs_302_2_t_disc.json")
        rids.append(a["rid"])
        b = _measure(P.FAR, "rs_302_2_t_temoin.json")
        rids.append(b["rid"])
        yield {"disc": a, "temoin": b}
    finally:
        for rid in rids:
            P.dispose(rid)


def test_cooldown_is_purged_before_measuring(arms):
    """G : sans la purge, « le natif ne propose pas 1169 » ne mesure que l'indisponibilite."""
    for k, r in arms.items():
        assert r["cooldown"] in (None, 0), (
            "bras %s : 1169 encore en cooldown (%s)" % (k, r["cooldown"]))


def test_per_stage_oracle_is_available(arms):
    """A : le RPC `pairUtility` accepte une cible TUILE (hooks #302-t5). ECHEC EXPLICITE sinon."""
    for k, r in arms.items():
        errs = [row["err"] for row in r["rows"] if row["err"]]
        assert not errs, (
            "bras %s : `pairUtility` refuse la cible TUILE (%s) -- le bundle Frida injecte est "
            "anterieur au correctif hooks #302-t5, il n'y a PAS d'oracle par etage : rebuild + "
            "reinject avant de conclure quoi que ce soit sur ce port" % (k, errs[0]))
        assert any(row["natType"] == 0 for row in r["rows"]), (
            "bras %s : aucune cible resolue comme EntityType.Tile -- le domaine n'est pas tuile" % k)


def test_montage_actually_reaches_the_predicate(arms):
    """Le bras DISCRIMINANT DOIT atteindre le regime ou le predicat est VRAI, sinon il ne mesure
    rien (c'est exactement le piege de la tranche 1 : hors regime, tout vaut 0 et tout « passe »)."""
    nz = [r for r in arms["disc"]["rows"] if (r["nat"] or 0) > 0]
    assert len(nz) >= 2, (
        "bras DISCRIMINANT : seulement %d tuile(s) a prediction non nulle -- l'aura "
        "`ContagionsOfNurgle` du caster ne couvre pas les occupants, le montage ne mord plus" % len(nz))
    assert all((r["nat"] or 0) == 0 for r in arms["temoin"]["rows"]), (
        "bras TEMOIN : le natif predit du degat alors que le caster est cense etre hors portee "
        "d'aura -- le temoin ne separe plus les deux regimes")


def test_prediction_covers_only_the_tile_occupant(arms):
    """F : au plus UN event par tuile (`GetMainDamageTarget`), jamais les ennemis ADJACENTS."""
    for k, r in arms.items():
        for row in r["rows"]:
            assert row["nev"] <= 1, (
                "bras %s tuile %s : %d events -- `GetAdjacentDamageTargets` a fuite dans le batch "
                "de prediction, or il n'y entre PAS" % (k, row["pos"], row["nev"]))


def test_prediction_fields_are_bit_exact_with_the_native_playbook(arms):
    """B : `aiPlaybookPredict` (le `MakeDamagePredictions` NATIF) rend, pour l'unite occupante, les
    MEMES bornes de degat que le port. Etage AMONT de l'utilite -- s'il diverge, tout le reste est
    du bruit."""
    r = arms["disc"]
    checked = 0
    for row in r["rows"]:
        if not row["fields"]:
            continue
        uid = next((i for i, v in r["units"].items() if v["pos"] == row["pos"]), None)
        assert uid is not None
        nat = L._rpc("aiPlaybookPredict", [{"runnerId": r["rid"], "unitId": r["caster"],
                                            "targetId": uid, "abilityType": PB}])
        assert nat.get("ok"), "aiPlaybookPredict KO: %s" % nat.get("error")
        evs = nat.get("events") or []
        assert len(evs) == 1, "natif : %d event(s) pour la cible u%s" % (len(evs), uid)
        f, n = row["fields"][0], evs[0]
        for key in ("healthDmgMin", "healthDmgMax", "hpBefore", "appliedHits"):
            assert int(f[key]) == int(n[key]), (
                "tuile %s champ %s : port %s != natif %s" % (row["pos"], key, f[key], n[key]))
        checked += 1
    assert checked >= 2, "moins de 2 cibles predites -- le montage ne couvre pas assez"


def test_the_shared_minmax_rounding_is_applied_and_the_gap_is_closed(arms):
    """C : le residu que cette garde ATTRIBUAIT est REFERME (#333). `MinMaxDamage$$Avg` =
    `(long)Fix64.Round((min+max)/2, midpointRounding = 0)` -- un arrondi DEMI-VERS-LE-PAIR --, et
    le port le fait desormais au foyer (`engine.services.min_max_damage.min_max_avg`, appele par
    les deux methodes de `DamageUtility`). L'ecart port/natif doit donc etre NUL sur TOUTES les
    tuiles, somme PAIRE comme IMPAIRE.

    Mesure avant/apres, meme montage : tuiles a somme IMPAIRE `+2.500e-03` -> `~8e-09`.

    ⚠ Cette garde ne vaut que si elle SAIT virer au rouge : elle rejoue donc le port d'AVANT #333
    (`(min+max)/2.0`, le `.5` conserve) en MUTATION et exige que l'ecart REAPPARAISSE sur les
    sommes IMPAIRES -- et seulement sur celles-la.

    Ce montage n'exerce QUE le cote `floor` IMPAIR du `.5` (bornes `3771 + 5652`), ou
    demi-vers-le-pair et demi-vers-le-haut COINCIDENT : il ne discrimine donc pas le MODE
    d'arrondi. C'est `tests/engine/test_333_minmax_avg_rounding_live.py` qui le fait, en pilotant
    la parite par les PV de la cible."""
    import engine.playbook as PBK
    import engine.utilities.damage as DMG

    r = arms["disc"]
    rows = [x for x in r["rows"] if x["fields"]]
    assert rows, "aucune tuile predite -- rien a mesurer"

    # (1) l'ecart est NUL des deux cotes de la parite.
    odd = 0
    for row in rows:
        f = row["fields"][0]
        s = int(f["healthDmgMin"]) + int(f["healthDmgMax"])
        d = (row["nat"] or 0.0) - (row["port"] or 0.0)
        odd += s % 2
        assert abs(d) < 1e-6, (
            "tuile %s : somme %s, ecart %.3e -- l'arrondi `MinMaxDamage$$Avg` n'est plus applique "
            "au foyer, ou un AUTRE residu est apparu"
            % (row["pos"], "IMPAIRE" if s % 2 else "PAIRE", d))
    assert odd >= 1, (
        "aucune somme IMPAIRE dans le montage -- aucun `.5` exact n'est exerce, l'accord ne dit "
        "alors RIEN de l'arrondi")

    # (2) MUTATION : le port d'AVANT #333 doit faire REAPPARAITRE l'ecart, sur les IMPAIRES seules.
    pb = PBK.REGISTRY[PB]
    orig = DMG.min_max_avg
    DMG.min_max_avg = lambda a, b: (int(a) + int(b)) / 2.0
    try:
        _s, _rpc, _dv, _mv, _wt, _pr, ctx = P._ctx(r["rid"], r["caster"])
        for row in rows:
            f = row["fields"][0]
            s = int(f["healthDmgMin"]) + int(f["healthDmgMax"])
            evs = pb.make_damage_predictions(ctx, ctx.origin, row["tile"], PB) or []
            mutated = pb.calculate_utility_from_predictions(ctx, ctx.origin, row["tile"], PB, evs)[0]
            d = (row["nat"] or 0.0) - mutated
            if s % 2:
                assert abs(d) > 1e-4, (
                    "tuile %s : somme IMPAIRE et la MUTATION (le `.5` conserve) ne change RIEN "
                    "(ecart %.3e) -- la garde ne sait pas virer au rouge" % (row["pos"], d))
            else:
                assert abs(d) < 1e-6, (
                    "tuile %s : somme PAIRE et la MUTATION change quelque chose (ecart %.3e) -- "
                    "l'arrondi mordrait hors du regime `.5`" % (row["pos"], d))
    finally:
        DMG.min_max_avg = orig


def test_engine_matches_native_on_both_arms(arms):
    """Le moteur reproduit le choix NATIF (ability ET tuile) dans les DEUX bras."""
    for k, r in arms.items():
        assert r["accord"], "bras %s : moteur %s != natif %s" % (k, r["engine"], r["native"])
        assert r["native"][0] == PB, (
            "bras %s : le natif ne caste pas 1169 (%s) -- le montage ne mord plus" % (k, r["native"]))


def test_prediction_term_changes_the_chosen_tile(arms):
    """D : dans le bras DISCRIMINANT, vider `MakeDamagePredictions` fait choisir une AUTRE tuile.
    C'est la preuve que cette garde SAIT virer au rouge (une garde jamais vue rouge ne prouve rien)."""
    r = arms["disc"]
    assert r["engine"] != r["mutated"], (
        "la mutation (terme de prediction vide) ne change RIEN : le montage n'atteint pas le "
        "regime discriminant, l'accord ne prouve donc pas que le terme est porte")
    assert r["mutated"][0] == PB, (
        "sans le terme, le moteur change d'ABILITY (%s) : le montage teste alors 1169-vs-69, pas "
        "la CIBLE -- la discrimination visee est celle de la TUILE" % (r["mutated"],))
    assert r["engine"][1] != r["mutated"][1]


def test_prediction_term_is_inert_outside_the_regime(arms):
    """E : hors du regime (predicat FAUX partout), le terme est un no-op EXACT -- la tranche 1
    (qui mesurait `0` partout) reste vraie telle quelle."""
    r = arms["temoin"]
    assert r["engine"] == r["mutated"], (
        "bras TEMOIN : la mutation change la decision (%s -> %s) alors que tous les termes de "
        "prediction valent 0 -- le port ajoute une utilite INVENTEE hors regime"
        % (r["engine"], r["mutated"]))
    assert all((row["port"] or 0.0) == 0.0 for row in r["rows"]), (
        "bras TEMOIN : le port predit du degat la ou le natif n'en predit pas")
