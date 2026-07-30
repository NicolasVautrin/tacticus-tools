"""#195 — GARDE de l'AUTRE argument de la face DECISION : `isPreventOverkill` = result@+0xb3.

CE QUE CE FICHIER VERROUILLE. Le 5e argument de la surcharge PRIVEE 8-args d'
`IdunBattle.Core.Services.DamagePrediction$$IsOverkill` entre par DEUX portes distinctes, et le
port passait `0` EN DUR aux deux :

  * `IdunBattle.Core.Services.DamagePredictionResult$$WillBeOverkill` et `$$MightBeOverkill` le
    lisent dans `result@+0xb3` — les DEUX, a la difference d'`isCritical` dont l'asymetrie est
    NATIVE (#R34) ;
  * `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` le calcule
    LUI-MEME sur son parametre `defender` (`uVar1 = UnitExtensions.HasFlag(defender, 0x13)`) juste
    avant son propre `IsOverkill`, dont le verdict pilote le cap Resilient.

Le corps prive ne teste `pct` que `if (!isPreventOverkill && targetInitialHealth <= healthDamage)` :
flag pose => retour 0, quelle que soit la sur-frappe. Le port comptait donc `PossibleOverkill`
(utilite 37) sur toute cible portant `UnitFlag.PreventOverkill` (=19, `enums.tsv`), pose par le SEUL
ecrivain du binaire `FuelledByFury_BlockOverkillEffect$$ApplyInternal` (porteur `ultraTitus`, #178).

DEUX GARDES, ET LA PREMIERE EST LA PLUS IMPORTANTE :

 1. CANAL — `preventOverkill` prend-il DEUX valeurs ? Un champ qui ne rend jamais que son defaut est
    INDISCERNABLE d'un champ mort, et aucun test d'egalite ne peut faire la difference : c'est la
    reserve explicite sous laquelle #190 avait ete livre (« critere FAIBLE assume »), et c'est CETTE
    garde qui la leve. Meme runner, meme attaquant, deux cibles.

 2. UTILITE — formule ISOLEE : les deux cotes sont nourris des MEMES predictions NATIVES, le natif
    etant le scoreur invoque en direct (`pairUtility`). Tout ecart est donc un gap de LOGIQUE,
    jamais de feed. Mesure AVANT le fix : natif 133.2826 vs port 148.2826 sur `ultraTitus` =
    **exactement PossibleOverkill (15.0)**, et 0 ecart sur `genesPrimus` aux MEMES bornes RAW.
    Le temoin tourne le MEME montage : la ou le flag est faux, le fix ne doit RIEN deplacer.

REGIME OBLIGATOIRE (garde 2) : `PV <= rawMax < 2 x PV` avec crit force. C'est la seule fenetre ou
`MightBeOverkill` depend d'un argument : au-dessus, l'overkill est NATUREL et les deux variantes
coincideraient — un montage hors regime rendrait VERT sans rien mesurer.

Montage : `scripts/python/probe_195_prevent_overkill_decision.py` ; fixtures : `conftest.py`.
"""
from __future__ import annotations

import probe_195_prevent_overkill_decision as PVO


# ── 1. CANAL ────────────────────────────────────────────────────────────────────────────────────

def test_prevent_overkill_takes_two_distinct_values(prevent_overkill_channel_case):
    """Le champ DESCEND **et** DISCRIMINE : vrai sur le porteur du flag 0x13, faux sur le temoin.

    Sans cette garde, le canal expose par #190 resterait indiscernable d'un canal mort — et un port
    qui cesserait de lire `result@+0xb3` ne serait rattrape par aucun test d'egalite."""
    r = prevent_overkill_channel_case()
    a, b = r.get(PVO.CARRIER) or {}, r.get(PVO.CONTROL) or {}
    assert not a.get("error") and not b.get("error"), (
        "montage casse : %s / %s" % (a.get("error"), b.get("error")))
    # L'INSTRUMENT avant la MECANIQUE : si le decodeur de `ProbableDamageEvent` derape, le champ
    # sous test vaut 0 des deux cotes pour une raison qui n'a rien a voir avec le flag 0x13. Le
    # dire ICI evite d'accuser le port (ou le roster) d'une panne de canal (#268).
    assert r.get("channel_alive"), "%s -- sentinelles : %s" % (PVO._CHANNEL_DEAD,
                                                               r.get("channel_why"))
    assert a.get("preventOverkill"), (
        "`%s` porte `FuelledByFury_BlockOverkill` (flag 0x13) des le deploiement (#178) : le champ "
        "doit valoir VRAI. Lu : %r" % (PVO.CARRIER, a.get("preventOverkill")))
    assert not b.get("preventOverkill"), (
        "`%s` ne porte pas le flag : le champ doit valoir FAUX. Lu : %r"
        % (PVO.CONTROL, b.get("preventOverkill")))
    assert len(r.get("distinct_values") or []) >= 2, (
        "une seule valeur observee (%s) : le canal ne se distingue pas d'un canal mort"
        % (r.get("distinct_values"),))


# ── 2. UTILITE (formule isolee) ─────────────────────────────────────────────────────────────────

def test_carrier_utility_matches_native_only_with_the_key(prevent_overkill_utility_case):
    """Sur le PORTEUR : le port AVEC la cle == le natif, et le port SANS s'ecarte d'EXACTEMENT
    `PossibleOverkill`. C'est la garde qui CHIFFRE le terme — pas seulement « les deux cotes sont
    d'accord ». La variante SANS reproduit le port d'avant #195 sans revenir en arriere dans le
    code, donc la garde reste capable de rougir."""
    m = prevent_overkill_utility_case(PVO.CARRIER)
    ok, why = PVO._verdict_utility(m, expect_flag=True)
    assert m["lethal_below_threshold"], (
        "regime non atteint — PV %s, bornes RAW [%s,%s] (il faut PV <= rawMax < 2 x PV ET "
        "rawMin < PV, sinon l'overkill est NATUREL et l'argument ne sert a rien)"
        % (m["hp"], m["raw_min"], m["raw_max"]))
    assert m["might_crit"] is True, (
        "crit non force : `MightBeOverkill` n'atteint pas le cas « letal mais sous le seuil », "
        "le terme sous test est QUIESCENT et la garde ne mesure rien")
    assert m["prevent_overkill"] is True, (
        "`%s` ne porte plus le flag 0x13 : le montage a perdu sa variable" % PVO.CARRIER)
    assert m["port_might_overkill_with"] is False, (
        "`might_be_overkill` doit rendre FAUX quand le flag est pose — le corps prive sort avant "
        "le test de pct")
    assert m["port_might_overkill_without"] is True, (
        "sans la cle, `might_be_overkill` doit rendre VRAI : sinon la paire ne discrimine plus "
        "rien et le VERT ne prouve pas que la cle est LUE")
    assert ok, why


def test_control_target_is_untouched(prevent_overkill_utility_case):
    """NON-REGRESSION : la ou le flag est FAUX, le fix ne doit RIEN deplacer — les deux variantes
    egalent le natif. Une degradation symetrique (marquer « pas d'overkill » partout) passerait la
    garde du porteur mais tomberait ici."""
    m = prevent_overkill_utility_case(PVO.CONTROL)
    ok, why = PVO._verdict_utility(m, expect_flag=False)
    assert m["prevent_overkill"] is False, (
        "`%s` porte le flag : ce n'est plus un temoin" % PVO.CONTROL)
    assert m["port_might_overkill_with"] == m["port_might_overkill_without"] is True, (
        "sur le temoin, la cle ne doit rien changer et l'overkill doit rester VRAI "
        "(avec=%s sans=%s)" % (m["port_might_overkill_with"], m["port_might_overkill_without"]))
    assert ok, why


def test_will_be_overkill_also_reads_the_flag(prevent_overkill_utility_case):
    """ASYMETRIE BORNEE : `WillBeOverkill` passe `isCritical = 0` EN DUR (#R34) mais lit BIEN
    `result@+0xb3` — l'asymetrie native porte sur le 3e argument, PAS sur le 5e. Ce test verrouille
    la lecture VERBATIM du decompile contre une « harmonisation » qui retirerait la cle de la borne
    garantie en croyant preserver l'asymetrie de #R34.

    ⚠ Au regime PV = rawMax, `WillBeOverkill` sort AVANT le test de pct : son verdict est FAUX des
    deux cotes et cette garde est QUIESCENTE ici. Elle documente l'invariant ; c'est le verdict
    d'utilite du porteur qui MESURE."""
    m = prevent_overkill_utility_case(PVO.CARRIER)
    assert m["port_will_overkill_with"] is False, (
        "`WillBeOverkill` rend VRAI sur un porteur du flag : le 5e argument n'est pas lu par la "
        "borne garantie alors que le natif l'y passe")
