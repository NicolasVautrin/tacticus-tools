"""#462-r4e-o-r1 -- GARDE OFFLINE de la CARDINALITE des events `Amount` en regime OVERKILL.

Le natif applique le degat UN COUP A LA FOIS (`IdunBattle.Operations.ApplyDamageOperation$$Execute`,
un appel par coup), et son SITE (A) PRECEDE toute emission :

    cVar15 = IdunBattle_Entities_UnitExtensions__HasFlag(target, 8);   // UnitFlag.Overkilled
    if (cVar15 != '\\0') {
      ApplyDamageOperation__RecordHitStatistics(...);
      ApplyDamageOperation__AddLeftoverHit(..., 1, 0);
      return param_1;                                 // <- ni PV mutes, ni evenement
    }

Le flag, lui, est pose PAR CE MEME `Execute`
(`IdunBattle.Entities.Components.UnitFlagsComponent$$Add(flags, 8)` sous
`dar.didOverkill && UnitExtensions.CanBeOverkilled(target)`), et le `didOverkill` vient de la
surcharge d'INSTANCE d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`, qui accumule
`(targetHealthBeforeAttack.Value - UnitExtensions.GetStat(target, Health)) + healthComponent@+0x24`
-- le degat APPLIQUE plus le degat GASPILLE (l'accumulateur de sur-reduction de
`IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`, nomme par `...$$ResetOverReduce`).

CE QUE CE FICHIER GARDE, et pourquoi OFFLINE : le live (`test_overkill_amount_live.py`) confronte
les VALEURS a quatre regimes de bataille, mais il ne peut pas montrer POURQUOI la coupure tombe au
coup 3 et pas au coup 2 -- c'est de l'arithmetique per-coup. Ici on la joue directement, aux
memes chiffres que les regimes mesures, et on ARME la contre-epreuve (le foyer de mutation
`overkill_hit_emits`) pour prouver que la garde MORD.

ASCII only.
"""
from __future__ import annotations

from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations import damage_hits as DH
from engine.runner.operations.damage_hits import HitDamage, overkill_flag_posted_by_hit
from engine.runner.prng import IntBasedMersenneTwister

# Les quatre regimes MESURES live (cf. `case-462-r4e-o-amount-borne-aux-pv.md` §4 et §5).
MULTI_CADAVRE = (2000, 2400, 4)      # MC1_67/31337 `--hp-target 2000` : live = [2000, 0]
SURVIVANT = (999999, 2400, 4)        # MC1_67/31337 `--hp-target 999999` : la cible survit


def _salve(hp, dmg, hits, **kw):
    """Une salve de `hits` coups DEGENERES a `dmg`, sur une cible a `hp` PV."""
    hd = HitDamage(dmg, dmg)
    return AttackDamageOperation._run_hits(
        IntBasedMersenneTwister(777), hd, hd, 0, False, hits, None,
        hp_current=hp, hp_floor=None, **kw)


def test_deux_coups_apres_la_mort_ne_produisent_QU_UN_event():
    """LE cas du residu : `live=[2000, 0]`, pas `[2000, 0, 0, 0]`.

    Le coup 1 TUE sans doubler les PV (2400 < 2 x 2000) -> `didOverkill` FAUX, aucun flag. Le coup
    2 rend `2400 + (2000 - 0) = 4400 >= 4000` -> flag POSE, mais il emet quand meme (le
    `UnitFlagsComponent.Add` precede l'emission DANS le meme `Execute`). Les coups 3 et 4 entrent
    sur le SITE (A) et ne produisent RIEN."""
    r = _salve(*MULTI_CADAVRE)
    assert r["per_hit"] == [2000, 0], r["per_hit"]
    assert r["hits_executed"] == 4 and r["overkill_suppressed"] == 2
    assert r["overkilled"] is True and r["overkill_at_hit"] == 1


def test_la_coupure_tombe_au_coup_QUI_SUIT_celui_qui_pose_le_flag():
    """Le flag ne gate pas le coup qui le pose. C'est ce decalage d'UN coup qui separe `[2000, 0]`
    (natif) de `[2000]` -- un modele « le coup letal coupe tout » serait AUSSI faux."""
    r = _salve(*MULTI_CADAVRE)
    assert len(r["per_hit"]) == r["overkill_at_hit"] + 1, (
        "les events emis doivent s'arreter APRES le coup qui pose le flag : %s / at=%s"
        % (r["per_hit"], r["overkill_at_hit"]))


def test_l_etat_final_et_la_somme_sont_INCHANGES():
    """L'ecart etait de RAPPORT seul : meme somme d'`Amount`, memes PV retires. C'est pour ca
    qu'aucun test d'ETAT ne pouvait le voir."""
    r = _salve(*MULTI_CADAVRE)
    assert sum(r["per_hit"]) == MULTI_CADAVRE[0]          # exactement les PV de depart
    assert r["per_hit_health"] == [2400] * 4              # le DEMANDE reste per-coup, full-length
    assert r["denied_before"] == [0] * 4


def test_cible_qui_survit_aucun_gate():
    """Temoin : hors overkill le flag n'est jamais pose et les 4 coups emettent."""
    r = _salve(*SURVIVANT)
    assert r["per_hit"] == [2400] * 4
    assert r["overkilled"] is False and r["overkill_suppressed"] == 0


def _rejoue(hp, coups):
    """Re-joue une salve HETEROGENE a la main : `Amount` par coup + pose du flag, en tenant
    l'accumulateur `+0x24` comme le natif (`Reduce` l'alimente APRES la lecture d'`IsOverkill`)."""
    hp_left, over, out, ovk, at = hp, 0, [], False, None
    for i, brut in enumerate(coups):
        if ovk:
            out.append(None)                     # SITE (A) : aucun event
            continue
        entry, over_entry = hp_left, over
        amount, hp_left = DH.damage_amount_applied(brut, 0, hp_left, None)
        over += max(0, brut - (entry - hp_left))
        out.append(amount)
        if overkill_flag_posted_by_hit(brut, 0, hp, entry, over_reduce_before=over_entry):
            ovk, at = True, i
    return out, ovk, at


def test_regime_cadavre_mesure_AUCUNE_suppression():
    """C3_01/777 (`[2764, 3787, 2289, 2203]` sur 7530 PV) : la cible meurt au coup 3, un 4e coup
    tombe sur le cadavre -- et le natif emet bien QUATRE events. Le cumul n'atteint jamais
    2 x 7530, donc le flag n'est JAMAIS pose : la borne per-coup (#462-r4e-o) suffit ici, la
    cardinalite est intacte. C'est ce regime qui interdit de rabattre « un coup sur cadavre » sur
    « un coup supprime »."""
    out, ovk, _ = _rejoue(7530, (2764, 3787, 2289, 2203))
    assert out == [2764, 3787, 979, 0] and not ovk


def test_regime_cadavre_sans_flag_mesure_le_TERME_0x24():
    """MC1_67/31337 `--hp-target 4000`, rolls `[3583, 3181, 3947, 4012]` -> natif `[3583, 417, 0]`.

    C'est LE regime qui a fait apparaitre `healthComponent@+0x24` : sans lui, le coup 3 rend
    `3947 + 4000 = 7947 < 8000` et le flag tombe au coup 4 (donc QUATRE events). Avec le degat
    gaspille par le coup 2 (`3181 - 417 = 2764`), il rend `10711` et le flag tombe au coup 3."""
    out, ovk, at = _rejoue(4000, (3583, 3181, 3947, 4012))
    assert out == [3583, 417, 0, None] and ovk and at == 2
    # contre-modele : le meme re-jeu SANS le terme `+0x24` mettrait le flag un coup trop tard.
    assert overkill_flag_posted_by_hit(3947, 0, 4000, 0, over_reduce_before=0) is False
    assert overkill_flag_posted_by_hit(3947, 0, 4000, 0, over_reduce_before=2764) is True


def test_flag_deja_pose_a_l_entree_supprime_TOUS_les_coups():
    """`overkilled0` = le flag pose par une sous-operation PRECEDENTE (phase d'arme -> groupe de
    coups additionnels). Le natif relit `HasFlag(target, 8)` a chaque `Execute`, donc la
    suppression traverse les sous-operations de l'attaque."""
    r = _salve(2000, 2400, 4, overkilled0=True)
    assert r["per_hit"] == [] and r["overkill_suppressed"] == 4 and r["hits_executed"] == 4


def test_can_be_overkilled_FAUX_desarme_la_pose():
    """`UnitFlagsComponent.Add(8)` est gate par `UnitExtensions.CanBeOverkilled` (trait Steppable),
    et `IsOverkill` le teste lui aussi en premier -> aucun gate, tous les coups emettent."""
    r = _salve(*MULTI_CADAVRE, can_be_overkilled=False)
    assert r["per_hit"] == [2000, 0, 0, 0] and r["overkilled"] is False


def test_prevent_overkill_desarme_la_pose():
    """`UnitExtensions.HasFlag(target, 0x13 = PreventOverkill)` (FuelledByFury_BlockOverkill) :
    `IsOverkill` rend FAUX quel que soit le degat -> aucune suppression."""
    r = _salve(*MULTI_CADAVRE, prevent_overkill=True)
    assert r["per_hit"] == [2000, 0, 0, 0] and r["overkilled"] is False


def test_CONTRE_EPREUVE_le_foyer_de_mutation_fait_re_diverger():
    """Retirer le correctif AU FOYER (`overkill_hit_emits` toujours VRAI) doit restaurer EXACTEMENT
    le port d'avant #462-r4e-o-r1 : `[2000, 0, 0, 0]`. Si cette assertion passe sans mutation,
    c'est que la garde ne mord pas."""
    ref = _salve(*MULTI_CADAVRE)["per_hit"]
    orig = DH.overkill_hit_emits
    try:
        DH.overkill_hit_emits = lambda overkilled: True
        muted = _salve(*MULTI_CADAVRE)
    finally:
        DH.overkill_hit_emits = orig
    assert ref == [2000, 0] and muted["per_hit"] == [2000, 0, 0, 0], (ref, muted["per_hit"])
    assert sum(muted["per_hit"]) == sum(ref), "la mutation ne doit changer que la CARDINALITE"
    assert _salve(*MULTI_CADAVRE)["per_hit"] == ref, "restauration du foyer KO"


def test_les_deux_termes_natifs_somment_au_DEGAT_DEMANDE_cumule():
    """IDENTITE qui reconcilie le port : `(hp_start - hp_left)` est le degat APPLIQUE des coups
    precedents et `+0x24` le degat GASPILLE -- leur somme est le degat DEMANDE cumule. C'est
    exactement ce que re-joue `AttackDamageOperation._did_overkill`, qui n'est donc PAS un modele
    concurrent. On l'assertionne sur une salve ou les deux termes sont non nuls."""
    hp, coups = 1000, (1600, 500)
    hp_left, over = hp, 0
    for i, brut in enumerate(coups):
        entry, over_entry = hp_left, over
        _, hp_left = DH.damage_amount_applied(brut, 0, hp_left, None)
        over += max(0, brut - (entry - hp_left))
        # le terme natif complet == le cumul des degats DEMANDES jusqu'a ce coup inclus
        assert brut + (hp - entry) + over_entry == sum(coups[:i + 1])
    assert (hp - hp_left) + over == sum(coups)


def test_over_reduce_HERITE_avance_la_pose_du_flag():
    """Le SEUL axe ou les deux formes se separent DANS une bataille : `+0x24` n'est jamais remis a
    zero (`ResetOverReduce` sans xref de code), donc une unite RESSUSCITEE apres avoir ete
    sur-reduite entre dans l'attaque suivante avec un compteur non nul -- et son premier coup peut
    poser le flag. Un re-jeu par « degat demande de CETTE attaque » ne peut pas le voir."""
    assert overkill_flag_posted_by_hit(1200, 0, 1000, 1000, over_reduce_before=0) is False
    assert overkill_flag_posted_by_hit(1200, 0, 1000, 1000, over_reduce_before=900) is True
