"""HealingBalms_Heal (1212) -- le COEFFICIENT du terme custom, MESURE live (#286).

Ce que la garde precedente ne couvrait PAS. `test_healing_balms_heal_decision_live.py` verifie que
le PORT applique bien `1.5 x U` / `1.0 x U` selon le gate, et l'A/B causal de la tranche #27-4d
verifiait que le NATIF bascule quand le gate se ferme -- mais il opposait deux cibles dont l'ecart
d'utilite de soin etait NUL (`pairUtility` bit-identique des deux cotes). Sur un tel montage,
n'importe quel terme strictement positif -- y compris une CONSTANTE -- fait basculer le natif de la
meme facon : le coefficient `Half` n'y etait discrimine par aucune mesure, seulement par la lecture
de `IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$CalculateCustomUtility`
(`Fix64$$FastMul(Sum(CalculateUtilityFromHealEvent), Fix64.<statics+0x30> = Half)`).

Ce que CE test garde : quatre bras a ecart d'utilite NON NUL, dont le classement natif s'INVERSE.
Cible A porte le gate (`EffectType.HealingBalms_ExtraCritDamage`, custom annule -> `u_A = U_A`),
cible B ne le porte pas (`u_B = (1 + c) U_B`), et le caster est FIGE (`Movement = 0` -> une seule
tuile candidate, terme de tuile rigoureusement commun aux deux options) :

  * bras 7 / 8 -- ratios 1.499894 et 1.500094, soit +-1e-4 autour de 1.5 : le natif bascule ENTRE
    LES DEUX. Ils ne se contentent pas d'exclure les valeurs rondes, ils MESURENT
    `0.4999 < c < 0.5001` ;
  * bras 1 / 4 -- ratio 1.40 au niveau HAUT et 1.60 au niveau BAS (utilites separees d'un facteur 4) :
    une CONSTANTE additive devrait valoir > 10.71 pour le premier et < 3.52 pour le second. Aucune ne
    satisfait les deux : la forme additive est refutee par la MESURE, plus seulement par le decompile.

Le montage complet (huit bras, plus les controles de generalisation sur un autre board, un autre seed
et un autre couple de cibles) vit dans `scripts/python/probe_286_healingbalms_coefficient.py`.

Le regime est choisi NON SATURE (`missing > healAmount`) : `U = 100 x healAmount / (hpMax + 1)` n'y
depend plus que de `hpMax`, donc ni le soin RETARDE du passif (~4986) ni les coups adverses ne
deplacent la mesure -- c'est ce qui rend le montage pilotable la ou piloter `missing` par les degats
ne l'etait pas.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

PINCE = (7, 8)          # bras a +-1e-4 de 1.5 : ils MESURENT le coefficient
NIVEAUX = (1, 4)        # bras a deux NIVEAUX d'utilite : ils refutent la forme additive
ARMS_UNDER_GUARD = PINCE + NIVEAUX
HALF = "half (decompile)"


@pytest.fixture(scope="module")
def arms(live_session):
    """Joue les quatre bras du montage. Un controle de montage qui echoue LEVE (`RuntimeError`) et
    fait ECHOUER le test : un montage impossible ne doit jamais se degrader en skip -- un skip est
    VERT et mentirait sur ce qui a ete mesure."""
    import probe_286_healingbalms_coefficient as P

    logs = P.ROOT / "logs"
    base = P.base_seed_bc(logs / "bc_286_base.json")
    return {n: P.run_arm(live_session, n, base, logs) for n in ARMS_UNDER_GUARD}


def test_native_ranking_inverts_with_the_heal_utility_gap(arms):
    """Le classement natif s'INVERSE alors que le gate reste pose du MEME cote. C'est le fait brut
    que l'A/B a ecart nul ne pouvait pas produire."""
    import probe_286_healingbalms_coefficient as P

    for n, r in arms.items():
        want = P.ARMS[n]["expect"]
        assert r["native_target_role"] == want, (
            "bras %d (niveau %s, ratio %.6f, U_A=%.9f U_B=%.9f) : le natif retient %s, attendu %s"
            % (n, P.ARMS[n]["level"], r["ratio"], r["U_A"], r["U_B"],
               r["native_target_role"], want))
    for lo, hi in (PINCE, NIVEAUX):
        assert arms[lo]["native_target_role"] != arms[hi]["native_target_role"], \
            f"bras {lo} et {hi} rendent le meme classement : rien n'est discrimine"


def test_multiplicative_coefficient_is_measured_at_half(arms):
    """`u_A = U_A` (gate ferme) contre `u_B = (1 + c) U_B` : chaque bras borne `c` d'un cote. Les
    deux bras PINCE encadrent `Half` a 1e-4 pres -- c'est une mesure du coefficient, pas seulement
    une exclusion de valeurs rondes."""
    c_lo = max(r["c_lo"] for r in arms.values() if r["c_lo"] is not None)
    c_hi = min(r["c_hi"] for r in arms.values() if r["c_hi"] is not None)
    assert c_lo < 0.5 < c_hi, \
        f"encadrement mesure {c_lo:.6f} < c < {c_hi:.6f} : Half (0.5) n'y est PAS"
    assert c_hi - c_lo < 1e-3, \
        (f"encadrement {c_lo:.6f} < c < {c_hi:.6f} trop LARGE ({c_hi - c_lo:.6f}) : les bras pinces "
         f"n'ont pas joue leur role, la valeur n'est pas mesuree")


def test_additive_constant_form_is_refuted_by_contradiction(arms):
    """Une CONSTANTE `k` ajoutee aux cibles non gatees devrait franchir l'ecart `U_A - U_B` au
    niveau HAUT (bras 1) et ne pas le franchir au niveau BAS (bras 4). Les deux exigences sont
    incompatibles."""
    k_lo, k_hi = arms[1]["k_lo"], arms[4]["k_hi"]
    assert k_lo is not None and k_hi is not None, "bornes additives absentes"
    assert k_lo >= k_hi, (
        "aucune contradiction : une constante k dans [%.6f, %.6f] passerait les deux bras -- "
        "les deux niveaux d'utilite sont trop proches pour separer additif et multiplicatif"
        % (k_lo, k_hi))


def test_engine_matches_native_and_each_arm_separates_the_forms(arms):
    """Le port (facteur `Half`) reproduit le choix natif dans les QUATRE bras, et chaque bras SEPARE
    au moins une forme concurrente -- un bras que toutes les formes passent ne mesure rien."""
    import probe_286_healingbalms_coefficient as P

    for n, r in arms.items():
        assert r["forms"].get(HALF) == r["native_target_role"], (
            "bras %d : moteur (Half) -> %s, natif -> %s"
            % (n, r["forms"].get(HALF), r["native_target_role"]))
        diverging = [k for k, v in r["forms"].items() if k != HALF and v != r["native_target_role"]]
        assert diverging, \
            "bras %d : aucune forme concurrente ne diverge (%s) -- bras non discriminant" \
            % (n, r["forms"])
    # la forme ADDITIVE calibree sur le niveau HAUT doit casser au niveau BAS : c'est la
    # contradiction du test precedent, rendue visible cote moteur.
    const = "const %.1f" % P.K_CONST
    assert arms[1]["forms"].get(const) == arms[1]["native_target_role"], \
        "la constante calibree ne passe meme pas le bras ou elle a ete calibree"
    assert arms[4]["forms"].get(const) != arms[4]["native_target_role"], \
        "la constante calibree sur le niveau HAUT passe aussi le niveau BAS : montage non separant"
