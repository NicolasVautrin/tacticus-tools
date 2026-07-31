"""Le `+1` d'utilite d'ACTION de l'attaque NORMALE (#64) -- GARDE de non-regression, LIVE.

NATIF (relu au decompile sur `rnca9r7q6c` -- TROIS corps DISTINCTS, a trois adresses distinctes ;
ce n'est donc pas une deduplication IL2CPP mal lue) :

    IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility
        -> FixMath.NET.Fix64$$op_Implicit(0)                          # la BASE rend Fix64(0)
    IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility
        -> FixMath.NET.Fix64$$op_Implicit(1)                          # Fix64(1)
    IdunBattle.AI.Playbook.Idun.NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility
        -> FixMath.NET.Fix64$$op_Implicit(1)                          # Fix64(1)
    IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$CalculateCustomUtility
        -> FixMath.NET.Fix64$$op_Implicit(1)                          # Fix64(1)

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
somme ce terme (vtable +0x338) AVANT `CalculateUtilityFromPredictions`, avant le gate `ShouldExecute`
(+0x328) et avant `CalculateUtilityFromTilePrediction` : il entre donc dans TOUS les argmax. Une
attaque normale bat ainsi tout autre actif Comparable tant que
`u_pair(autre) - u_pair(normale) < 1` a tuile egale.

POURQUOI CETTE GARDE EXISTE. Le terme etait porte (`engine.playbook.common.NormalAttackPlaybook.
calculate_custom_utility` -> `1.0`) et JUSTE, mais son unique datapoint vivait dans un OUTIL DE
DIAGNOSTIC (`scripts/python/engine_agreement_stages.py`, seed 2468 pas 18). Aucune suite ne le
retenait : le neutraliser ne faisait rougir aucun test. La degradation est SILENCIEUSE (l'IA joue une
autre ability, sans erreur ni crash) -- exactement le profil qu'un entrainement irait exploiter.

CE QUE LA GARDE EPROUVE, et pourquoi chaque moitie est necessaire :
  * le montage doit ENCADRER la bascule native (un bras 1191, un bras attaque normale), sinon il
    mesure une preference ecrasante ou le `+1` ne pese rien ;
  * dans le bras « fenetre », le scorer natif de PAIRE (`pairUtility`) classe 1191 DEVANT l'attaque
    normale, d'un ecart strictement inferieur a 1 -- et le natif joue quand meme la normale. C'est la
    mesure du `+1` par le natif lui-meme, pas un raisonnement ;
  * le moteur doit SUIVRE le natif dans les deux bras (c'est LE test qui rougit si le `+1` disparait
    du port) ;
  * le MEME moteur dont on force le terme a `0.0` doit BASCULER sur 1191 -- sans quoi le montage
    serait un angle mort et son accord ne prouverait rien.

MONTAGE : fixture `normal_attack_bonus_case` (cf. `tests/engine/conftest.py` ->
`probe_308_normal_attack_bonus`). Kariyan (`custoBladeChampion`) seul, passif retire, cible amenee au
CONTACT ; curseur `--unit-stat custoBladeChampion:Damage=<D>` qui deplace l'attaque normale et PAS
1191 (base entierement config, verifie par `test_the_cursor_moves_only_the_normal_attack`).

NON COUVERT, et nomme expres :
  * `ProperKilly_NormalAttackPlaybook$$CalculateCustomUtility` est une AUTRE loi (melee + comparaison
    de PV : `Fix64(HP(cible) + 1)`, ou `BaseUtility.<statics+0x18>` quand la cible n'est pas celle a
    plus haut PV en melee). Elle n'est PAS portee et ce fichier ne la garde pas ;
  * la valeur exacte du terme (1 plutot que 2) n'est demontree ici que par ENCADREMENT : l'ecart de
    paire franchit 1.0 au meme `Damage` que la bascule native. Un terme de 2 aurait bascule ailleurs ;
  * le gate `ShouldExecute` et les trois sentinelles `BaseUtility` (voie `NO_ACTION`) sont hors
    perimetre -- le custom teste ici est numerique.

ASCII only."""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_308_normal_attack_bonus as NAB                 # noqa: E402

MARTIAL_INSPIRATION = NAB.MARTIAL_INSPIRATION               # 1191, l'actif Comparable du duel

# GENERALISATION -- second couple (board, seed, cible), calibre par la MEME bisection au pas de 1.
# MESURE (2026-07-30, `rnca9r7q6c`) : la bascule native y est a Damage 1397 / 1398, dans un regime
# numerique tout AUTRE (pair 8.7850 / 9.8019 au lieu de 20.8714 / 21.9021) -- et elle tombe encore
# EXACTEMENT au franchissement de 1.0 (gap 1.0169 -> 0.9959). C'est ce qui montre que le terme est un
# `+1` ABSOLU, pas un facteur relatif : un bonus proportionnel aurait bascule ailleurs.
# Cf. `test_the_bonus_generalises_to_another_board_and_target`.
GEN = {"board": "C3_01", "seed": 777, "target": "ultraCalgar", "damages": (1397, 1398)}

# TROISIEME couple -- une cible qui porte un TRAIT GATANT un modificateur de degat de l'attaquant.
# `tauCrisis` <<Re'vas>> porte `BigTarget`, donc le `BeastSlayer_ExtraDmg` de Kariyan (+20 % melee)
# entre dans les DEUX abilities du duel.
#
# Ce bras etait litteralement documente comme "CIBLE A EVITER" jusqu'au 2026-07-31 : le port
# sous-predisait 1191 (raw [1496,2244] au lieu de [1795,2692]) parce que
# `generate_multi_hit_attack_prediction` ne threadait pas `target_traits` -- residu `N16`, ferme par
# #316. Le montage y rendait V2 = 1/2 bras, pour une raison ETRANGERE au `+1`.
# Il passe desormais 2/2 (MESURE 2026-07-31, bisection au pas de 1) :
#     Damage=1187 : pair(69)=20.2580  pair(1191)=21.2822  gap=1.0243 > 1  -> natif ET moteur -> 1191
#     Damage=1188 : pair(69)=20.2864  pair(1191)=21.2822  gap=0.9958 < 1  -> natif ET moteur -> 69
# Il garde donc DEUX choses a la fois : le `+1` (l'objet de ce fichier) et la CONSEQUENCE DECISION
# du threading de #316 -- si ce dernier regressait, `pair(1191)` retomberait a 17.7352, le gap
# passerait a -2.5 et le moteur ne suivrait plus le natif dans le bras temoin.
GEN_GATED = {"board": "C3_01", "seed": 777, "target": "tauCrisis", "damages": (1187, 1188)}


def _arms(res) -> tuple:
    """`(bras temoin, bras fenetre)` = les deux `Damage` du scenario, dans l'ordre croissant."""
    ds = res["damages"]
    return res["rows"][ds[0]], res["rows"][ds[-1]]


def _label(res) -> str:
    return "%s/%s vs %s" % (res["board"], res["seed"], res["target"])


# ---------------------------------------------------------------- validite du MONTAGE
def _assert_montage(res):
    """Un montage qui n'encadre pas la bascule ne mesure RIEN : il rougit ICI, il ne skippe pas."""
    lo, hi = _arms(res)
    lab = _label(res)
    assert lo["normal"] == hi["normal"], \
        (f"[{lab}] l'id d'attaque normale change entre les deux bras "
         f"({lo['normal']} vs {hi['normal']}) -- ce n'est plus le meme duel")
    na = hi["normal"]
    assert lo["native"] == MARTIAL_INSPIRATION, (
        f"[{lab}] bras TEMOIN (Damage={lo['damage']}) : le natif joue {lo['native']} au lieu de "
        f"{MARTIAL_INSPIRATION} -- la bascule n'est plus encadree, le montage est hors zone et ne "
        f"conclut RIEN. Re-calibrer : `python probe_308_normal_attack_bonus.py --auto "
        f"--board {res['board']} --seed {res['seed']} --target {res['target']}`.")
    assert hi["native"] == na, (
        f"[{lab}] bras FENETRE (Damage={hi['damage']}) : le natif joue {hi['native']} au lieu de "
        f"l'attaque normale {na} -- meme diagnostic, re-calibrer avec `--auto`.")
    for r in (lo, hi):
        assert r["pair_normal"] is not None and r["pair_1191"] is not None, (
            f"[{lab}] Damage={r['damage']} : `pairUtility` muet "
            f"(normale={r['pair_normal']}, 1191={r['pair_1191']}) -- l'oracle natif de paire n'a "
            f"rien rendu, rien n'est concluant")


def test_the_montage_brackets_the_native_flip(normal_attack_bonus_case):
    """Les deux bras encadrent bien la bascule native (1191 -> attaque normale). Sans cela, tout ce
    qui suit mesurerait une preference ecrasante ou le `+1` ne pese rien."""
    _assert_montage(normal_attack_bonus_case())


def test_the_cursor_moves_only_the_normal_attack(normal_attack_bonus_case):
    """CONFOND NEUTRALISE : le curseur `Damage` ne doit deplacer QUE l'attaque normale. La base de
    1191 vient entierement de la config d'ability
    (`MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext` :
    `round(minDmg x (extraDmgPct x TotalAttacksMade + 100)/100)`), pas du stat `Damage` du caster.
    Si les deux bougeaient, la bascule ne dirait plus rien sur l'ecart entre les deux abilities."""
    res = normal_attack_bonus_case()
    _assert_montage(res)
    lo, hi = _arms(res)
    assert lo["pair_1191"] == hi["pair_1191"], (
        f"[{_label(res)}] `pairUtility(1191)` VARIE avec le curseur : {lo['pair_1191']} "
        f"(Damage={lo['damage']}) vs {hi['pair_1191']} (Damage={hi['damage']}). Le curseur touche "
        f"AUSSI 1191 -- la bascule confond deux effets et l'encadrement de l'ecart est faux.")
    assert hi["pair_normal"] > lo["pair_normal"], (
        f"[{_label(res)}] `pairUtility(normale)` ne CROIT pas avec `Damage` "
        f"({lo['pair_normal']} -> {hi['pair_normal']}) : le curseur ne pilote rien")


def test_the_native_plays_the_normal_attack_although_its_own_scorer_ranks_1191_higher(
        normal_attack_bonus_case):
    """LA MESURE DU `+1` PAR LE NATIF LUI-MEME.

    Dans le bras FENETRE, `pairUtility` -- c.-a-d.
    `ComparablePlaybook<T>$$CalculateUtilityFromPredictions` invoque en direct, la valeur EXACTE que
    le bucket natif attribue a la paire, SANS terme Tile ni custom -- classe 1191 DEVANT l'attaque
    normale. Le natif joue pourtant la normale. L'ecart est strictement compris entre 0 et 1 : seul
    un bonus d'action de 1 pose sur la normale explique ce choix.

    Et le bras TEMOIN ferme l'autre cote : des que l'ecart DEPASSE 1, le natif repasse sur 1191."""
    res = normal_attack_bonus_case()
    _assert_montage(res)
    lo, hi = _arms(res)
    lab = _label(res)
    assert 0.0 < hi["gap"] < 1.0, (
        f"[{lab}] bras FENETRE (Damage={hi['damage']}) : pair(1191) - pair(normale) = {hi['gap']} "
        f"n'est PAS dans ]0, 1[ (pair(1191)={hi['pair_1191']}, pair(normale)={hi['pair_normal']}). "
        f"Le natif y joue l'attaque normale sans que le `+1` soit ce qui tranche : le montage ne "
        f"demontre plus rien. Re-calibrer avec `--auto`.")
    assert lo["gap"] > 1.0, (
        f"[{lab}] bras TEMOIN (Damage={lo['damage']}) : pair(1191) - pair(normale) = {lo['gap']} "
        f"n'excede PAS 1 alors que le natif y joue 1191 -- l'encadrement du terme a 1 ne tient plus "
        f"(un `+1` aurait suffi a faire gagner la normale).")


# ---------------------------------------------------------------- LA GARDE
def _assert_engine_follows_native(res):
    lo, hi = _arms(res)
    bad = [r for r in (lo, hi) if r["engine"] != r["native"]]
    assert not bad, (
        f"[{_label(res)}] le MOTEUR ne suit plus le natif : "
        + " | ".join(f"Damage={r['damage']} natif={r['native']} moteur={r['engine']} "
                     f"(pair normale={r['pair_normal']}, pair 1191={r['pair_1191']}, "
                     f"ecart={r['gap']})" for r in bad)
        + ". Le bras FENETRE se joue a MOINS d'un point d'utilite : le seul terme qui y decide est "
          "le `+1` d'action de l'attaque normale "
          "(`ALoki_NormalAttackPlaybook<T>$$CalculateCustomUtility` = `Fix64(1)`, base "
          "`ComparablePlaybook<T>$$CalculateCustomUtility` = `Fix64(0)`), somme par "
          "`ComparablePlaybook<T>$$CalculateActionUtility` AVANT tout argmax. Verifier que "
          "`engine.playbook.common.NormalAttackPlaybook.calculate_custom_utility` rend toujours "
          "`1.0` et que `ComparableAbilityGenerator._action_utility` l'ajoute toujours a `u_full`.")


def test_the_engine_follows_the_native_in_both_arms(normal_attack_bonus_case):
    """LA GARDE. Le moteur doit rendre la MEME action que le natif dans les deux bras -- y compris
    dans la fenetre a moins d'un point, ou seul le `+1` peut trancher. Neutraliser ce terme fait
    rougir CE test."""
    res = normal_attack_bonus_case()
    _assert_montage(res)
    _assert_engine_follows_native(res)


def test_neutralising_the_bonus_would_have_been_visible(normal_attack_bonus_case):
    """MUTATION ADVERSARIALE, embarquee dans le montage : le MEME moteur dont
    `NormalAttackPlaybook.calculate_custom_utility` est force a `0.0` le temps de l'appel DOIT
    basculer sur 1191 dans la fenetre, donc DIVERGER du natif. Sans cette moitie, l'accord du test
    precedent pourrait n'etre qu'un angle mort du montage."""
    res = normal_attack_bonus_case()
    _assert_montage(res)
    _, hi = _arms(res)
    assert hi["engine_zero_bonus"] == MARTIAL_INSPIRATION, (
        f"[{_label(res)}] avec le terme force a 0.0, le moteur rend encore "
        f"{hi['engine_zero_bonus']} au lieu de {MARTIAL_INSPIRATION} : le `+1` n'est PAS ce qui "
        f"decide sur ce montage, et l'accord moteur<->natif n'y prouve rien. Re-calibrer avec "
        f"`--auto`.")
    assert hi["engine_zero_bonus"] != hi["native"], (
        f"[{_label(res)}] le moteur MUTE rend la meme action que le natif ({hi['native']}) -- le "
        f"montage ne discrimine pas les deux hypotheses")


def test_the_ported_constants_mirror_the_native_bodies(normal_attack_bonus_case):
    """CLIQUET OFFLINE -- il ne prouve RIEN sur le natif (la preuve est dans les tests live
    ci-dessus), mais il nomme la constante et rougit instantanement si elle disparait."""
    res = normal_attack_bonus_case()
    assert res["ported_base"] == 0.0, (
        f"`ComparablePlaybook.calculate_custom_utility` rend {res['ported_base']!r} au lieu de 0.0 "
        f"-- la base native est `Fix64.op_Implicit(0)`")
    assert res["ported_normal"] == 1.0, (
        f"`NormalAttackPlaybook.calculate_custom_utility` rend {res['ported_normal']!r} au lieu de "
        f"1.0 -- les DEUX corps natifs de l'attaque normale rendent `Fix64.op_Implicit(1)`")


# ---------------------------------------------------------------- generalisation
def test_the_bonus_generalises_to_another_board_and_target(normal_attack_bonus_case):
    """GENERALISATION : meme mesure sur un AUTRE couple (board, seed, cible). Le `+1` n'est une
    propriete ni du terrain ni de la cible -- une reussite sur une seule geometrie ne demontrerait
    pas que le terme est le bon, seulement qu'il passe la ou il a ete calibre. La cible change AUSSI
    (armure/PV differents -> autre point d'equilibre du duel, donc autre `Damage` de bascule)."""
    res = normal_attack_bonus_case(board=GEN["board"], seed=GEN["seed"], target=GEN["target"],
                                   damages=GEN["damages"])
    _assert_montage(res)
    _, hi = _arms(res)
    assert 0.0 < hi["gap"] < 1.0, (
        f"[{_label(res)}] ecart de paire {hi['gap']} hors de ]0, 1[ dans la fenetre")
    _assert_engine_follows_native(res)
    assert hi["engine_zero_bonus"] == MARTIAL_INSPIRATION, (
        f"[{_label(res)}] la mutation a 0.0 ne fait pas basculer le moteur : le second couple "
        f"n'exerce pas le terme")


def test_the_bonus_generalises_to_a_target_whose_trait_gates_an_attacker_modifier(
        normal_attack_bonus_case):
    """GENERALISATION -- cible dont un TRAIT ouvre un modificateur de degat de l'ATTAQUANT.

    `tauCrisis` porte `BigTarget`, donc le `BeastSlayer_ExtraDmg` de Kariyan (+20 % melee) s'applique
    aux DEUX abilities du duel. Ce couple etait interdit d'usage jusqu'a #316, ou la prediction
    d'ability du port ne lisait pas les traits de la cible : il rendait alors `pair(1191) = 17.7352`
    au lieu de 21.2822 et le moteur ne suivait plus le natif -- pour une raison ETRANGERE au `+1`.

    Ce test garde donc DEUX invariants d'un coup : le `+1` (l'objet du fichier) et la CONSEQUENCE
    DECISION du threading `target_traits` de `generate_multi_hit_attack_prediction`."""
    res = normal_attack_bonus_case(board=GEN_GATED["board"], seed=GEN_GATED["seed"],
                                   target=GEN_GATED["target"], damages=GEN_GATED["damages"])
    _assert_montage(res)
    _, hi = _arms(res)
    assert 0.0 < hi["gap"] < 1.0, (
        f"[{_label(res)}] ecart de paire {hi['gap']} hors de ]0, 1[ dans la fenetre")
    _assert_engine_follows_native(res)
    assert hi["engine_zero_bonus"] == MARTIAL_INSPIRATION, (
        f"[{_label(res)}] la mutation a 0.0 ne fait pas basculer le moteur : ce couple n'exerce pas "
        f"le terme")
