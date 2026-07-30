"""MartialInspiration (1191) face PREDICTION -- la base de degat est indexee par le compteur
`TotalAttacksMade` LIVE, pas par son instantane du pas 0. GARDE de non-regression, LIVE.

NATIF (mirror relu sur `rnca9r7q6c`) :
    IdunBattle.AI.Playbook.Loki.MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext
        var12 = IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(cfg, 0xc)  # minDmg
        var10 = IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(cfg, 0xa)  # extraDmgPct
        count = <ActorStatisticsComponent>+0x20                                               # TotalAttacksMade
        base  = IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers(
                    Fix64(var12), Fix64.FromIntFraction(var10 * count + 100, 100) )
        hits  = 1 (litteral)
Ecrivain du compteur : `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackMade`
(`+0x20 += 1` a chaque attaque, appelee par `IdunBattle.Operations.RegisterAttackOperation$$Execute`) ;
lecteur cote formule : `IdunBattle.Entities.Formulas.TotalAttacksMadeFormula$$Calculate`.

POURQUOI CETTE GARDE EXISTE. Le port lit ce compteur par `scene.total_attacks_made` <-
`predictor["actorstats_by_id"]`, dont le COLD (`scene.build_predictor`, capte au pas 0) vaut 0 pour
tout le monde. Sans la RE-CAPTURE PAR PAS de `scene.refresh_shields`, la prediction reste collee a
`buff = 1` toute la bataille et SOUS-ESTIME des la 1re attaque du caster. La divergence avait ete
mesuree (#33, 31337 s16 : off 598-898 vs natif 994-1976) puis corrigee -- mais AUCUN test ne la
retenait : ni `actorStats`, ni `total_attacks_made`, ni `MartialInspiration`, ni `1191` n'apparaissaient
dans `tests/`. La degradation est SILENCIEUSE (une prediction plus basse, donc une cible d'IA
differente), donc invisible en self-play.

CE QUE LA GARDE EPROUVE, et pourquoi les deux moities sont necessaires :
  * le port FRAIS doit egaler le natif (`aiPlaybookPredict`) A CHAQUE TOUR ;
  * le MEME port dont on PERIME le seul canal `actorstats_by_id` (instantane du tour 0) doit
    DIVERGER des que le compteur a bouge. Sans cette seconde moitie, un port qui ignorerait le
    compteur passerait le premier test tant que le compteur vaut 0.

Montage : fixture `martial_inspiration_case` (cf. `tests/engine/conftest.py` ->
`probe_17_martial_inspiration`). Positions DRIVEES (cible amenee au contact), PV de la cible forces
tres haut pour qu'elle survive a toutes les attaques, predicteur COLD construit UNE FOIS et rafraichi
par pas -- la couture reelle de `engine_validate.run_agreement`.

NON COUVERT, et nomme expres : un ecart d'UNE unite sur les bornes existe au TOUR 0 (compteur = 0,
donc buff = 1) sur `MC1_63`/11922. Il n'est PAS imputable a ce canal -- le CONTROLE embarque dans le
montage (meme confrontation sur l'attaque NORMALE, meme pas, meme tuile, meme cible, qui ne passe ni
par `_martial_inspiration_inputs` ni par le compteur) diverge AUSSI a ce tour-la (natif rawMin 9486
vs port 9483) et est bit-exact aux tours suivants. Ecart AVAL du pipeline de degat au tout premier
pas de bataille, pre-existant, hors perimetre. La garde l'ATTRIBUE au lieu de le masquer : un ecart
de 1191 SANS ecart du controle rougit. ASCII only."""
from __future__ import annotations


def _assert_montage(res, label):
    """La garde ne vaut que si le compteur A REELLEMENT BOUGE pendant la mesure."""
    rows = res["rows"]
    assert len(rows) >= 2, f"[{label}] {len(rows)} tour(s) mesure(s) : il en faut au moins 2"
    counts = [r["count_live"] for r in rows]
    assert counts[0] == 0, \
        (f"[{label}] le compteur ne part pas de 0 (counts={counts}) -- le regime « debut de "
         f"bataille, buff = 1 » n'est pas couvert")
    assert max(counts) > 0, \
        (f"[{label}] TotalAttacksMade n'a jamais bouge (counts={counts}) : le caster n'a pas "
         f"attaque, la garde n'eprouve rien")
    for r in rows:
        assert r["native"] is not None, \
            (f"[{label}] tour {r['round']} : `aiPlaybookPredict` n'a rendu AUCUN event pour "
             f"l'ability 1191 -- oracle muet, rien n'est concluant")
        assert r["off_fresh"] is not None, \
            f"[{label}] tour {r['round']} : le port n'a produit aucune prediction pour 1191"
        assert r["count_seen_fresh"] == r["count_live"], \
            (f"[{label}] tour {r['round']} : la scene FRAICHE voit count={r['count_seen_fresh']} "
             f"alors que le live vaut {r['count_live']} -- le canal `actorStats` par-pas ne remonte "
             f"pas jusqu'a `scene.total_attacks_made`")
        assert r["count_seen_cold"] == res["cold0"], \
            (f"[{label}] tour {r['round']} : la scene MUTANTE voit count={r['count_seen_cold']} au "
             f"lieu de l'instantane du tour 0 ({res['cold0']}) -- la mutation n'est pas installee")


def _assert_fresh_matches_native(res, label):
    """Le port FRAIS doit egaler le natif -- avec UN garde-fou d'attribution, et pas un
    assouplissement : un ecart n'est tolere que s'il est AUSSI present sur le CONTROLE (l'attaque
    normale, meme pas, meme tuile, meme cible), qui ne passe ni par `_martial_inspiration_inputs`
    ni par le compteur. Un tel ecart est AVAL par construction. Un ecart SPECIFIQUE a 1191 rougit.

    MESURE (2026-07-30) : le seul ecart rencontre est au TOUR 0, sur `MC1_63`/11922 -- natif
    [4490, 6732] vs port [4489, 6731] -- et le controle 69 y diverge AUSSI (natif rawMin 9486 vs
    port 9483). Aux tours 1 et 2 les DEUX abilities sont bit-exactes. Residu AVAL nomme, hors
    perimetre du canal `actorStats`."""
    bad = []
    for r in res["rows"]:
        if not r["delta_fresh"]:
            continue
        ctrl = r.get("control_normal_attack")
        if ctrl is not None and ctrl.get("delta"):
            continue                      # meme ecart sur le controle -> etage AVAL, pas ce canal
        bad.append(r)
    assert not bad, (
        f"[{label}] la prediction offline de MartialInspiration (1191) DIVERGE du natif sur "
        f"{len(bad)} tour(s), SANS que l'attaque normale diverge au meme pas -- l'ecart est donc "
        f"SPECIFIQUE a 1191 : "
        + " | ".join(f"tour {r['round']} count={r['count_live']} nat={r['native']} "
                     f"off={r['off_fresh']} delta={r['delta_fresh']} "
                     f"controle={r.get('control_normal_attack')}" for r in bad)
        + ". Base native = round(minDmg x (extraDmgPct x TotalAttacksMade + 100)/100), hits=1 "
          "(`MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext`).")


def _assert_exact_when_counter_moved(res, label):
    """Le regime que le canal GOUVERNE (compteur > instantane du tour 0) doit etre BIT-EXACT --
    aucune tolerance, aucun garde-fou d'attribution."""
    moved = [r for r in res["rows"] if r["count_live"] > res["cold0"]]
    assert moved, f"[{label}] aucun tour a compteur > 0 : le regime discriminant n'est pas atteint"
    bad = [r for r in moved if r["delta_fresh"]]
    assert not bad, (
        f"[{label}] compteur > 0 et la prediction n'est PAS bit-exacte : "
        + " | ".join(f"tour {r['round']} count={r['count_live']} nat={r['native']} "
                     f"off={r['off_fresh']} delta={r['delta_fresh']}" for r in bad))


def _assert_stale_channel_would_diverge(res, label):
    moved = [r for r in res["rows"] if r["count_live"] > res["cold0"]]
    assert moved, \
        (f"[{label}] aucun tour ou le compteur depasse son instantane du tour 0 -- la contre-epreuve "
         f"n'est pas exercable")
    diverged = [r for r in moved if r["delta_cold"]]
    assert diverged, (
        f"[{label}] PERIMER le canal `actorstats_by_id` (instantane du tour 0) ne change RIEN a la "
        f"prediction : "
        + " | ".join(f"tour {r['round']} count={r['count_live']} nat={r['native']} "
                     f"cold={r['off_cold']}" for r in moved)
        + ". Le canal n'est donc pas load-bearing sur ce montage : soit le handler "
          "`_martial_inspiration_inputs` ne lit plus `scene.total_attacks_made`, soit le montage "
          "n'exerce plus le compteur -- dans les deux cas la garde ne protege plus rien.")


def test_martial_inspiration_prediction_follows_the_live_counter(martial_inspiration_case):
    """Le port suit le compteur LIVE : accord bit-exact avec `aiPlaybookPredict` a chaque tour,
    y compris apres que le caster a attaque (count > 0, buff > 1)."""
    res = martial_inspiration_case()
    _assert_montage(res, "MC1_67")
    _assert_fresh_matches_native(res, "MC1_67")
    _assert_exact_when_counter_moved(res, "MC1_67")


def test_stale_actorstats_channel_diverges_from_native(martial_inspiration_case):
    """CONTRE-EPREUVE : le MEME port dont on perime le seul canal `actorstats_by_id` diverge du
    natif des que le compteur a bouge. C'est ce qui rend le test precedent non vide."""
    res = martial_inspiration_case()
    _assert_montage(res, "MC1_67")
    _assert_stale_channel_would_diverge(res, "MC1_67")


def test_martial_inspiration_generalises_to_a_second_board(martial_inspiration_case):
    """GENERALISATION : meme mesure sur un AUTRE couple (board, seed). Le compteur et sa loi ne sont
    pas des proprietes du terrain -- une reussite sur une seule carte ne demontrerait rien."""
    res = martial_inspiration_case(seed=11922, board="MC1_63")
    _assert_montage(res, "MC1_63")
    _assert_fresh_matches_native(res, "MC1_63")
    _assert_exact_when_counter_moved(res, "MC1_63")
    _assert_stale_channel_would_diverge(res, "MC1_63")
