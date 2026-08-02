"""#419-r1-tr9-r4 -- le FOLD additional-damage fait traverser `nrOfHits` a `GetAttackHits`.

`IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction`
(et son JUMEAU au corps identique `RighteousRepugnance_NormalAttackAbility$$GetAdditionalDamagePrediction`)
ne passe PAS `GetNumberConstant(cfg, 0x2f)` comme compte de coups : il le passe au slot `0xb5` de
l'`IBattleQuery` -- `IdunBattle.Core.Services.BattleQuery$$GetAttackHits(attacker, defender,
hitGroupIndex, ability, attackWeaponHits)` -> `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` --
avec le MEME couple (caster, cible) que la base. `nrOfHits` est donc la BASE D'ARME du fold, et
TOUS les canaux de coups s'y appliquent, malus DEFENSEUR compris.

Le port prenait `nrOfHits` pour le compte final. Consequence mesuree (`templAggressor` ->
`necroWarden` sur `LightCover`) : natif `h2`, port `h4` -- un facteur ~2 sur les DEUX bornes de
degat, qui est exactement le residu `#419-r1-tr9-r4`.

CE QUE CE TEST GARDE -- cinq choses :

  1. **LES QUATRE REGIMES SONT INSTALLES** -- `build_case` ATTESTE chacun (terrain `DryBush` pour
     `LightCover`, adjacence NATIVE au porteur `BigTarget`, contact pour la gate `IsMelee`) et LEVE
     sinon. Sans ce cran, un accord pourrait etre celui d'un montage vide.
  2. **L'ACCORD EST EXACT, CHAMP A CHAMP** -- bornes RAW et `appliedHits`, natif == port, sur TOUTES
     les cibles de TOUS les regimes. Entiers, aucune tolerance.
  3. **LE MALUS TRAVERSE REELLEMENT LE FOLD** -- sur `cover` et `bigtarget`, le fold NATIF porte
     STRICTEMENT moins de coups que `nrOfHits`. C'est la lecture elle-meme, mesuree cote natif : le
     port n'entre pas dans sa definition (bras apparie `PassiveAbilities=[]`).
  4. **LA BASE D'ARME DU FOLD EST `nrOfHits`, PAS LES COUPS DE L'ARME** -- sur `melee`
     (`adeptMorvenn` : arme `Power` a 2 coups, `RighteousRepugnance.nrOfHits` = 3), le fold natif en
     porte 3. C'est le SEUL regime qui distingue les deux modeles ; sur `templAggressor` ils valent
     tous deux 3 et la mesure ne trancherait rien.
  5. **LES CONTRE-EPREUVES MORDENT** -- chaque mutant a un regime ou il DEPLACE le port. Critere =
     deplacement par rapport au port NON MUTE, jamais l'ecart au natif (un mutant inerte le
     satisferait des qu'un residu traine).
     ⚠ Et la reciproque est gardee : `hits_raw` NE DOIT PAS mordre sur `plain`. C'est ce qui
     interdit un « fix » qui deplacerait aussi les regimes ou l'ancien port etait DEJA juste.

ASCII only. Probe jumeau : `scripts/python/probe_419r1tr9_r4_boltstorm_pred.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr9_r4_boltstorm_pred as P

# Le bras apparie (2e runner) n'est monte que pour les regimes dont la DECOMPOSITION est
# load-bearing : `cover` porte la lecture corrigee, `melee` tranche la base d'arme. Sur `plain` et
# `bigtarget` l'accord TOTAL + `appliedHits` suffit, et deux runners de moins allegent le pump.
WITH_BASELINE = ("cover", "melee")
# `nrOfHits` des deux passifs concernes (gameconfig) -- ce que le fold vaudrait SANS malus.
NR_OF_HITS = 3


@pytest.fixture(scope="module")
def r4_results(live_session, rpc, build_runner, host):
    """Joue les QUATRE regimes, un a la fois, et LIBERE chaque runner avant de passer au suivant :
    la discipline `runner.md` interdit d'en tenir six jusqu'au teardown du module."""
    out = {}

    def _dispose(rid):
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)

    for regime in P.REGIMES:
        rid = build_runner(P.SEED, P.build_args(regime))["rid"]
        try:
            mk = ((lambda r=regime: build_runner(P.SEED, P.build_args(r, "base"))["rid"])
                  if regime in WITH_BASELINE else None)
            out[regime] = P.run_regime(live_session, rpc, rid, regime, mk, _dispose,
                                       with_mutants=True)
        except P.MontageError as e:
            pytest.fail(f"[{regime}] {e}", pytrace=False)
        finally:
            _dispose(rid)
    return out


def test_every_regime_is_installed(r4_results):
    """(1) LES QUATRE REGIMES SONT INSTALLES, et chacun porte ses trois lignes."""
    assert set(r4_results) == set(P.REGIMES)
    for regime, res in r4_results.items():
        assert len(res["rows"]) == len(P.FOES), (
            f"[{regime}] {len(res['rows'])} lignes mesurees au lieu de {len(P.FOES)}")
        # L'attaque normale doit etre la CONCRETE (la sous-classe qui surcharge `PredictAttack`) :
        # sur la generique `69` il n'y aurait aucun fold et tout le fichier serait vide de sens.
        assert res["case"]["ab"] != 69, (
            f"[{regime}] l'attaque normale live vaut 69 -- la sous-classe surchargeante n'est PAS "
            f"instanciee, aucun fold n'a lieu")


def test_fields_match_native_everywhere(r4_results):
    """(2) L'ACCORD EST EXACT, CHAMP A CHAMP, sur toutes les cibles de tous les regimes."""
    for regime, res in r4_results.items():
        for r in res["rows"]:
            n, p = r["native"], r["port"]
            assert (p["rawMin"], p["rawMax"], p["hits"]) == (n["rawMin"], n["rawMax"], n["hits"]), (
                f"[{regime}][{r['vis']}] le port diverge du natif : "
                f"port=({p['rawMin']}, {p['rawMax']}, h{p['hits']}) "
                f"natif=({n['rawMin']}, {n['rawMax']}, h{n['hits']}) -- ctx {r['ctx']}")


def test_defender_malus_traverses_the_fold(r4_results):
    """(3) LE MALUS TRAVERSE REELLEMENT LE FOLD -- lu cote NATIF, et decompose par le bras apparie
    la ou il existe. Sans ce cran, un port qui n'appliquerait AUCUN malus au fold passerait le test
    d'accord si le natif n'en appliquait pas non plus."""
    for regime in ("cover", "bigtarget"):
        res = r4_results[regime]
        focus = next(r for r in res["rows"] if r["focus"])
        wh = focus["ctx"]["weapon"]["hits"]
        assert focus["native"]["hits"] < wh + NR_OF_HITS, (
            f"[{regime}][{focus['vis']}] le natif applique {focus['native']['hits']} coups, soit le "
            f"total SANS malus ({wh} + {NR_OF_HITS}) -- le regime n'exerce aucun malus de coups et "
            f"ne prouve rien")
        if "native_fold" in focus:
            assert focus["native_fold"]["hits"] < NR_OF_HITS, (
                f"[{regime}][{focus['vis']}] le FOLD natif porte {focus['native_fold']['hits']} "
                f"coups = `nrOfHits` : le malus ne le traverse PAS, la lecture portee est fausse")
            assert focus["port_fold"] == focus["native_fold"], (
                f"[{regime}][{focus['vis']}] fold port {focus['port_fold']} != fold natif "
                f"{focus['native_fold']}")
        # Les TEMOINS du meme regime, eux, ne subissent aucun malus : c'est ce qui interdit de lire
        # un fix global la ou on veut un fix cible.
        for r in res["rows"]:
            if r["focus"]:
                continue
            assert r["native"]["hits"] == r["ctx"]["weapon"]["hits"] + NR_OF_HITS, (
                f"[{regime}][{r['vis']}] le temoin porte {r['native']['hits']} coups -- il subit "
                f"lui aussi un malus, le regime ne discrimine plus")


def test_fold_weapon_base_is_nrofhits(r4_results):
    """(4) LA BASE D'ARME DU FOLD EST `nrOfHits`, PAS LES COUPS DE L'ARME. Regime `melee` :
    `adeptMorvenn` a une arme a 2 coups et `RighteousRepugnance.nrOfHits` = 3 -- les deux modeles
    candidats y donnent des reponses DIFFERENTES, et le natif tranche."""
    res = r4_results["melee"]
    focus = next(r for r in res["rows"] if r["focus"])
    wh = focus["ctx"]["weapon"]["hits"]
    assert wh != NR_OF_HITS, (
        f"le regime melee ne discrimine RIEN : l'arme du caster porte {wh} coups, autant que "
        f"`nrOfHits` ({NR_OF_HITS}) -- les deux modeles y coincident")
    assert "native_fold" in focus, "le bras apparie du regime melee n'a pas ete monte"
    assert focus["native_fold"]["hits"] == NR_OF_HITS, (
        f"le FOLD natif porte {focus['native_fold']['hits']} coups, attendu `nrOfHits` = "
        f"{NR_OF_HITS} (les coups de l'arme valent {wh})")
    # La GATE, au passage : a distance l'arme choisie n'est PAS melee -> aucun fold, des deux cotes.
    for r in res["rows"]:
        if r["focus"]:
            continue
        assert (r["port"].get("meta") or {}).get("followup") is None, (
            f"[melee][{r['vis']}] le port folde a distance alors que la gate `IsMelee` est fausse")


def test_counter_probes_bite_somewhere(r4_results):
    """(5) LES CONTRE-EPREUVES MORDENT -- chacune dans au moins un regime. Un mutant sans regime ou
    il deplace le port ne garde RIEN (le vice de #439, transpose a une garde de tranche)."""
    for name in P.MUTANTS:
        where = [rg for rg, res in r4_results.items()
                 if any(m["mutant"] == name and m["bites"] for m in res["mutants"])]
        assert where, (
            f"la contre-epreuve `{name}` NE MORD dans AUCUN des {len(P.REGIMES)} regimes : l'axe "
            f"qu'elle coupe n'est exerce nulle part, elle ne garde rien")


def test_socle_is_untouched_by_the_fix(r4_results):
    """(5 bis) LA RECIPROQUE : sur `plain` -- aucune cible sous malus -- l'etat d'AVANT le fix
    (`hits_raw`) NE DOIT PAS deplacer le port. C'est ce qui atteste que le correctif est un
    RAFFINEMENT du compte de coups et non un decalage global : s'il mordait ici, il aurait casse
    tous les regimes que #446-r1 avait deja mis en accord."""
    m = next(x for x in r4_results["plain"]["mutants"] if x["mutant"] == "hits_raw")
    assert not m["bites"], (
        f"sur le socle `plain`, `hits_raw` deplace le port de {m['shift']} -- le fix change des "
        f"regimes SANS malus de coups, ce qu'aucune lecture ne justifie")
