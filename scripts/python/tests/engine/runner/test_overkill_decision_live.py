"""#R34 — GARDE de la face DECISION de l'overkill : `MightBeOverkill` passe `MightCrit@+0xb1`.

CE QUE CE FICHIER VERROUILLE. `IdunBattle.Core.Services.DamagePredictionResult$$MightBeOverkill`
appelle la surcharge PRIVEE 8-args de `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` en lui
passant, au 3e argument (`isCritical`), le champ `MightCrit@+0xb1` du resultat ; son jumeau
`…$$WillBeOverkill` y passe **0 EN DUR** (litteral lu au desassemblage du site d'appel). Le corps
prive RENVOIE `isCritical` dans le cas « letal mais SOUS le seuil » :

    if (initialHealth <= healthDamage) return pct < overkillDmgPctOfHealth ? isCritical : true;

Le port passait 0 des DEUX cotes -> la borne OPTIMISTE de l'IA (`PossibleOverkill`, feuille
`OverkillUnit` = utilite 37) SOUS-ESTIMAIT tout kill critique dans `[PV, 2 x PV)`.

TROIS ETAGES, TROIS GARDES (le canal est verrouille de bout en bout : POSE **et** LU) :

 1. SOURCE du flag — `MightCrit` = `IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)`
    = `GetStat(9 CritChance) >= 1 && GetStat(10 CritDamage) > 0`, appele par
    `…$$PredictAttackRaw` lui-meme (interface `IDamageCalculations`, slot 7, store INCONDITIONNEL).
    Garde : le flag LIVE et le port coincident sur les regimes `100,1` / `100,0` / `0,1` -- les deux
    regimes a une seule conjonction vraie interdisent de conclure d'une correlation triviale.
    Garde PRODUCTEUR : `composite_fields()["mightCrit"]` (offline) == `mightCrit` de l'event NATIF.

 2. CANAL D'UTILITE — formule ISOLEE : les deux cotes sont nourris des MEMES predictions NATIVES,
    le natif etant le scoreur invoque en direct
    (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`,
    RPC `pairUtility`). Tout ecart est donc un gap de LOGIQUE, jamais de feed. Mesure AVANT le fix :
    natif 148.2903 vs port 133.2903 = **exactement PossibleOverkill (15.0)**, et 0 ecart dans le
    regime sans crit.

 3. CLASSEMENT — le terme deplace un CHOIX : deux cibles, le port d'AVANT prefere B, le natif et le
    port d'APRES preferent A.

REGIME OBLIGATOIRE (les etages 2 et 3) : `PV <= degat < 2 x PV`. Hors de la, l'overkill est
NATUREL et le flag ne sert a rien -- c'est le piege paye sur la face COMBAT (#R33), ou `aiPredict`
avait fait tuner les PV sur une preview fausse de 30 %.

Montage : `scripts/python/probe_r34_overkill_decision.py` ; fixtures : `conftest.py` de la tranche.
"""
from __future__ import annotations


# ── 1. SOURCE du flag ───────────────────────────────────────────────────────────────────────────

def test_might_crit_is_could_crit(overkill_decision_source_case):
    """`MightCrit` LIVE == `CouldCrit(attaquant)` = `GetStat(9) >= 1 ET GetStat(10) > 0`.

    Les trois regimes couvrent la CONJONCTION : `100,1` vraie, `100,0` et `0,1` fausses. Sans les
    deux derniers, un port qui lirait `MightCrit = CritDamage > 0` (ou l'inverse) passerait aussi."""
    r = overkill_decision_source_case()
    assert r["total"] > 0, "aucune paire mesuree : montage casse"
    bad = [x for x in r["rows"] if not x["agree"]]
    assert not bad, ("`pred.mightCrit` live != CouldCrit(attaquant) sur %d paires : %s"
                     % (len(bad), bad[:3]))
    seen = {k: sorted(set(v)) for k, v in r["regimes"].items()}
    assert seen.get("crit-on") == [True], (
        "le regime `100,1` doit rendre `mightCrit` VRAI partout : %s" % seen)
    assert seen.get("chance-only") == [False] and seen.get("dmg-only") == [False], (
        "les regimes a UNE SEULE conjonction vraie doivent rendre `mightCrit` FAUX (sinon la "
        "correlation ne prouve pas que les DEUX GetStat sont lus) : %s" % seen)


def test_offline_producer_matches_native_flag(overkill_decision_source_case):
    """PRODUCTEUR : `ProbableDamageEvent.composite_fields()["mightCrit"]` (chaine OFFLINE
    `attacker_could_crit` -> `predict_attack_raw` -> `DamagePredictionResult.might_crit`) ==
    `mightCrit` de l'event NATIF. C'est la garde qui tombe si la cle cesse d'etre POSEE."""
    r = overkill_decision_source_case()
    bad = [x for x in r["rows"] if not x["producer_agree"]]
    assert not bad, ("le producteur offline ne pose pas le meme flag que le natif sur %d paires "
                     ": %s" % (len(bad), bad[:3]))
    vals = {x["offline_might_crit"] for x in r["rows"]}
    assert vals == {True, False}, (
        "le producteur doit prendre LES DEUX valeurs sur ces regimes (sinon la garde ne "
        "discrimine rien) : %s" % vals)


# ── 2. CANAL D'UTILITE (formule isolee) ─────────────────────────────────────────────────────────

def test_utility_channel_matches_native_scorer(overkill_decision_utility_case):
    """L'utilite du PORT nourrie des events NATIFS == le scoreur NATIF, dans LES DEUX regimes.

    C'est la garde qui tombe si `might_be_overkill` cesse de LIRE la cle : l'ecart redevient
    exactement `PossibleOverkill` dans le regime crit, et 0 dans l'autre."""
    r = overkill_decision_utility_case()
    for tag in ("crit-off", "crit-on"):
        m = r[tag]
        assert m["lethal_below_threshold"], (
            "%s : regime non atteint -- PV %s, bornes RAW [%s,%s] (il faut PV <= rawMax < 2 x PV "
            "ET rawMin < PV, sinon l'overkill est NATUREL et le flag ne sert a rien)"
            % (tag, m["hp"], m["raw_min"], m["raw_max"]))
        assert m["force_overkill"] is False, (
            "%s : `ForceOverkill` est VRAI -> l'overkill ne discrimine plus le crit (attaquant "
            "porteur de ThrillSeekers ?)" % tag)
        assert m["native_utility"] is not None and m["port_utility"] is not None, (
            "%s : utilite illisible (pairUtility/aiPlaybookPredict KO)" % tag)
        assert abs(m["native_utility"] - m["port_utility"]) < 1e-3, (
            "%s : DESACCORD utilite port/natif sur des predictions IDENTIQUES (natif %.4f, port "
            "%.4f, ecart %.4f) -- gap de FORMULE, pas de feed"
            % (tag, m["native_utility"], m["port_utility"],
               m["native_utility"] - m["port_utility"]))
    assert r["crit-on"]["might_crit"] is True and r["crit-off"]["might_crit"] is False, (
        "la paire n'est plus discriminante : `mightCrit` doit differer entre les deux regimes")


def test_possible_overkill_is_exactly_the_delta(overkill_decision_utility_case):
    """La paire crit-on / crit-off DOIT separer, et l'ecart DOIT valoir `PossibleOverkill`.

    Le port d'AVANT (`isCritical = 0`) rendait un delta NUL ; le natif rend 15.0. C'est la garde
    qui chiffre le terme -- pas seulement « les deux cotes sont d'accord »."""
    r = overkill_decision_utility_case()
    w = r["possible_overkill_weight"]
    assert w > 0, "poids BC `PossibleOverkill` nul : le montage ne peut rien mesurer"
    assert abs(r["native_delta"] - w) < 1e-3, (
        "le natif ne gagne PAS exactement PossibleOverkill en passant crit-off -> crit-on "
        "(delta %.4f vs poids %.4f) : le regime a change" % (r["native_delta"], w))
    assert abs(r["port_delta"] - w) < 1e-3, (
        "le PORT ne suit pas : delta %.4f vs %.4f attendu -- `might_be_overkill` ne lit plus "
        "`mightCrit` (0 = le comportement d'avant #R34)" % (r["port_delta"], w))
    assert r["crit-on"]["port_might_overkill"] is True, (
        "avec crit, `might_be_overkill` doit rendre VRAI sur ce regime letal-sous-le-seuil")
    assert r["crit-off"]["port_might_overkill"] is False, (
        "sans crit, `might_be_overkill` doit rendre FAUX -- sinon le fix marque overkill TOUT "
        "kill sous le seuil (degradation symetrique)")
    assert r["crit-on"]["port_will_overkill"] is False \
        and r["crit-off"]["port_will_overkill"] is False, (
        "`WillBeOverkill` passe `isCritical = 0` EN DUR : il ne doit JAMAIS bouger avec le crit "
        "(l'asymetrie des deux bornes est NATIVE)")


def test_will_be_overkill_ignores_the_crit_flag(overkill_decision_utility_case):
    """ASYMETRIE des deux bornes, dans le SEUL regime qui la rend observable.

    A PV = borne RAW **MIN**, les DEUX bornes sont letales et sous le seuil : `WillBeOverkill`
    atteint alors le test `pct < overkillDmgPctOfHealth` et son verdict SERAIT `isCritical` s'il le
    lisait. Le natif y passe **0 EN DUR** -> `DefinitelyOverkill` (40) ne doit PAS s'allumer.
    ⚠ Cette garde est la seule a mordre : au regime PV = rawMax, `WillBeOverkill` sort AVANT le
    test de pct et une mutation qui lui cablerait `mightCrit` reste QUIESCENTE (verifie)."""
    m = overkill_decision_utility_case()["crit-on-min"]
    assert m["min_lethal_below_threshold"], (
        "regime non atteint : PV %s, borne RAW MIN %s (il faut PV <= rawMin < 2 x PV)"
        % (m["hp"], m["raw_min"]))
    assert m["might_crit"] is True, "regime sans crit : il ne discrimine rien"
    assert m["port_will_overkill"] is False, (
        "`WillBeOverkill` a suivi le flag crit alors que le natif y passe 0 EN DUR -> le port "
        "compte DefinitelyOverkill la ou le jeu compte PossibleOverkill")
    assert m["port_might_overkill"] is True, (
        "`MightBeOverkill` doit rendre VRAI ici (crit, letal, sous le seuil)")
    assert abs(m["native_utility"] - m["port_utility"]) < 1e-3, (
        "DESACCORD utilite port/natif au regime borne-MIN (natif %.4f, port %.4f) : les deux "
        "bornes ne sont plus traitees comme le natif les traite"
        % (m["native_utility"], m["port_utility"]))


# ── 3. CLASSEMENT ───────────────────────────────────────────────────────────────────────────────

def test_possible_overkill_changes_the_choice(overkill_decision_rank_case):
    """Le terme deplace un CHOIX, pas seulement un scalaire : sur une paire de cibles craftee, le
    port d'AVANT prefere B la ou le NATIF prefere A -- et le port d'APRES rejoint le natif.

    2e PORTEUR (`orksRuntherd`) et 2e regime (les deux cibles descendues dans DEUX bandes
    d'overkill distinctes) : le montage d'utilite, lui, tourne sur `ultraInceptorSgt` a PV fixes."""
    r = overkill_decision_rank_case()
    assert not r.get("noop"), (
        "la descente de PV n'a rien mute (`applyAction ok=True` sans mutation) : le montage n'a "
        "jamais demarre, aucune conclusion possible")
    f = r.get("flip")
    assert f is not None, (
        "aucune bascule de classement trouvee sur les seeds essayes -- trace : %s" % (r["trace"],))
    assert f["argmax_native"] == f["argmax_port_after"] != f["argmax_port_before"], (
        "la bascule n'est pas celle attendue : natif=%s port_avant=%s port_apres=%s"
        % (f["argmax_native"], f["argmax_port_before"], f["argmax_port_after"]))
    a_bef, b_bef = f["port_before"]["A"], f["port_before"]["B"]
    a_aft, b_aft = f["port_after"]["A"], f["port_after"]["B"]
    assert abs(b_aft - b_bef) < 1e-3, (
        "la cible B ne doit PAS bouger (son overkill est inconditionnel : `pct >= 100`) -- "
        "%.4f -> %.4f : le montage ne compare plus une bande crit-dependante a une bande "
        "inconditionnelle" % (b_bef, b_aft))
    assert a_aft > a_bef, (
        "la cible A doit GAGNER le terme (elle seule est letale-sous-le-seuil) : %.4f -> %.4f"
        % (a_bef, a_aft))
    assert b_bef > a_bef and a_aft > b_aft, (
        "l'inversion doit etre STRICTE des deux cotes : avant A=%.4f B=%.4f, apres A=%.4f B=%.4f"
        % (a_bef, b_bef, a_aft, b_aft))
