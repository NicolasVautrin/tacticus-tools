"""#178 — GARDE des GATES D'UNITE de `IdunBattle.Core.Services.DamagePrediction$$IsOverkill`
(surcharge d'INSTANCE, celle du chemin COMBAT).

CE QUE CE FICHIER VERROUILLE, et pourquoi il peut le verrouiller : le port hebergeait DEUX
`is_overkill` -- un mirror 1:1 de la surcharge 7-args PRIVEE (`services/trait_damage_limits.py`) et un
corps 2-args (`services/damage_prediction.py`) qui etait la surcharge d'INSTANCE AMPUTEE de ses gates
d'unite. C'est le corps AMPUTE que le chemin combat consommait
(`AttackDamageOperation._fire_death_if_killed`), donc c'est lui qui decidait `UnitFlag.Overkilled (8)`
et les `overkill=` des vecteurs de mort.

La PAIRE de regimes est la mesure : MEME attaquant (Shiron, melee), MEME degat, MEMES PV (400),
SEULE la victime change.
  * `control` (genesPrimus)  : aucun gate            -> le jeu marque overkill.
  * `titus`   (ultraTitus)   : `FuelledByFury_BlockOverkill` (1354) pose `UnitFlag.PreventOverkill`
    (0x13) -> le jeu NE marque PAS overkill, alors que `dmg (1452) >= 2 x PV (800)`.
Un seul des deux regimes ne conclurait rien : `control` seul ne distingue pas les deux corps, et
`titus` seul ne prouve pas que l'observable reagit.

OBSERVABLE : `TerrifyingCrescendo` (branche `On(UnitDeath) & OwnerIsActor & TargetIsOverkilled`, et
`IdunBattleLogic.Entities.DSLTriggers$$TargetIsOverkilled` = `HasFlagAbilityTrigger(target, 8)`)
incremente `TerrifyingCrescendo_ExtraDmg` sur le tueur -- niveau lisible dans
`decisionView.units[].effects[]`. Montage : `scripts/python/probe_178_overkill_gate.py`.

#R33 (2026-07-28) — MEME fichier, MEME fixture, deux regimes de plus (`crit` / `nocrit`) plus un
2e montage a observable INDEPENDANT (`overkill_revive_case`). Ce qu'ils verrouillent : le 3e
argument de la surcharge d'instance, **`isCritical`** (`DealDamageInfo@+0x1c`), que le port passait
a **0 EN DUR**. Le corps prive le RENVOIE dans le cas « letal mais sous le seuil » :

    if (initialHealth <= healthDamage) return pct < overkillDmgPctOfHealth ? isCritical : true;

donc tout crit qui tue sans doubler les PV EST un overkill. Le montage revive (Narthecium
« unless Overkilled », tueur `ultraInceptorSgt` SANS le trait `ThrillSeekers`) attribue
l'observation a `isCritical` et pas au rider ThrillSeekers.

#268 (2026-07-30) — D'OU VIENT LE DEGAT. Les regimes ne sont plus situes par une PREDICTION mais
par une MESURE LIVE : passe 1 a MEME seed / MEME compo / MEME geometrie avec la victime INCREVABLE
(`--hp-target 200000`), cast en live, `hp_avant - hp_apres`. Le tirage est REPRODUCTIBLE a seed et
sequence egales (mesure : 2375/2375/2375), donc la passe 1 rend le tirage EXACT de la passe 2.
Deux regimes, tranches sur cette seule mesure :
  * `above_threshold`        = `degat >= 2 x PV` -> overkill NATUREL (les gates d'unite, #178) ;
  * `lethal_below_threshold` = `PV <= degat < 2 x PV` -> le verdict depend d'un ARGUMENT (#R33).
Mesures : `control`/`titus` PV 400 degat 2375 ; `crit` PV 2256 degat 2774 ; `nocrit` PV 2256
degat 2375 -- crescendo 0 -> 1 avec crit, 0 -> 0 sans.
Motif du changement : `aiPredict` rendait `[1,100]` pour TOUT couple (decodeur a offsets perimes,
`docs/rl/case-268-decodeur-prediction-perime.md`), ce qui faisait SKIPPER cinq de ces tests en
accusant le roster. Les fixtures ECHOUENT desormais, elles ne skippent plus.
"""
from __future__ import annotations


def test_overkill_gate_control_reacts(overkill_gate_case):
    """CONTROL — sans gate, un coup a `dmg >= 2 x PV` EST un overkill (le compteur monte).
    C'est la contre-epreuve de discriminance : sans elle, un `titus` a +0 pourrait juste vouloir dire
    « l'observable ne reagit jamais »."""
    r = overkill_gate_case("control")
    assert r["above_threshold"], (
        "regime non atteint : degat LIVE %s < 2 x PV %s" % (r["live_damage"], r["hp"]))
    assert r["can_be_overkilled"] is True and r["prevent_overkill"] is False, (
        "la victime de controle ne doit porter AUCUN gate : %s" % r)
    assert r["live_overkill"] is True, (
        "le jeu n'a pas marque overkill un coup de %s sur %s PV (crescendo %s -> %s)"
        % (r["live_damage"], r["hp"], r["live_level_before"], r["live_level_after"]))
    assert r["port_overkill"] == r["live_overkill"], r


def test_overkill_gate_prevent_overkill_is_read(overkill_gate_case):
    """TEST — `UnitFlag.PreventOverkill` bloque l'overkill. C'est la garde qui tombe si le gate
    `prevent_overkill` de `unit_is_overkill` est retire (ou si `unit_prevents_overkill` cesse de
    deriver le flag de l'effet `FuelledByFury_BlockOverkill` qui le pose)."""
    r = overkill_gate_case("titus")
    assert r["above_threshold"], (
        "regime non atteint : degat LIVE %s < 2 x PV %s" % (r["live_damage"], r["hp"]))
    assert r["prevent_overkill"] is True, (
        "gate non vu offline : ultraTitus doit porter `FuelledByFury_BlockOverkill` -> %s" % r)
    assert r["live_overkill"] is False, (
        "le jeu a marque overkill une cible PreventOverkill (crescendo %s -> %s) : le regime a change"
        % (r["live_level_before"], r["live_level_after"]))
    assert r["port_overkill"] == r["live_overkill"], (
        "DESACCORD port/live sur la cible PreventOverkill : port=%s live=%s (%s)"
        % (r["port_overkill"], r["live_overkill"], r))


def test_overkill_gate_pair_is_discriminating(overkill_gate_case):
    """La paire DOIT separer les deux corps : meme degat, memes PV, verdicts LIVE opposes -- et le
    corps 2-args supprime repondait « overkill » des DEUX cotes."""
    ctl, tit = overkill_gate_case("control"), overkill_gate_case("titus")
    assert ctl["hp"] == tit["hp"] and ctl["above_threshold"] and tit["above_threshold"], (
        "les deux regimes ne sont plus comparables : PV %s/%s, degat LIVE %s/%s (les deux doivent "
        "etre >= 2 x PV, sinon le verdict cesse d'etre force par la seule sur-frappe)"
        % (ctl["hp"], tit["hp"], ctl["live_damage"], tit["live_damage"]))
    assert ctl["live_overkill"] != tit["live_overkill"], (
        "la paire n'est plus discriminante : le live rend le meme verdict des deux cotes")
    assert ctl["legacy_overkill"] is True and tit["legacy_overkill"] is True, (
        "le corps 2-args supprime devait dire `overkill` des DEUX cotes : %s / %s"
        % (ctl["legacy_overkill"], tit["legacy_overkill"]))
    assert ctl["port_overkill"] is True and tit["port_overkill"] is False, (
        "le corps livre doit suivre le live : %s / %s" % (ctl["port_overkill"], tit["port_overkill"]))


# ---------------------------------------------------------------------------------------------
# #R33 -- `isCritical` (`DealDamageInfo@+0x1c`), le 3e argument de la surcharge d'instance.
#
# `IsOverkill` RENVOIE `isCritical` dans le cas « letal MAIS sous le seuil » :
#     if (initialHealth <= healthDamage) return pct < overkillDmgPctOfHealth ? isCritical : true;
# Le port passait ce champ a 0 EN DUR -> il ne marquait JAMAIS overkill un crit letal sous 2x PV.
# REGIME : PV tunes a `dmin` et `dmax < 2 x PV` -> TOUTE la plage de degat est letale ET sous le
# seuil, donc le verdict ne depend que du flag crit (pas du tirage).
# ---------------------------------------------------------------------------------------------


def test_overkill_crit_below_threshold_is_overkill(overkill_gate_case):
    """CRIT — un coup CRITIQUE qui tue SANS doubler les PV EST un overkill (le compteur monte)."""
    r = overkill_gate_case("crit")
    assert r["lethal_below_threshold"], (
        "regime non atteint : degat LIVE %s vs PV %s (il faut PV <= degat < 2 x PV)"
        % (r["live_damage"], r["hp"]))
    assert r["is_crit_regime"] and all(r["replay_crits"]), (
        "le regime devait rendre TOUS les coups critiques : %s" % (r["replay_crits"],))
    assert r["live_overkill"] is True, (
        "le jeu n'a PAS marque overkill un crit letal de %s sur %s PV (crescendo %s -> %s)"
        % (r["live_damage"], r["hp"], r["live_level_before"], r["live_level_after"]))
    assert r["port_replay_overkill"] == r["live_overkill"], (
        "DESACCORD port/live : le REJEU de l'attaque par le port n'a pas pose UnitFlag.Overkilled "
        "(port=%s live=%s, total=%s crits=%s)"
        % (r["port_replay_overkill"], r["live_overkill"], r["replay_total"], r["replay_crits"]))


def test_overkill_nocrit_below_threshold_is_not_overkill(overkill_gate_case):
    """NON-CRIT — MEME plage de degat, MEMES PV, mais aucun crit possible (`CouldCrit` faux car
    `GetStat(CritDamage) == 0`) : le jeu NE marque PAS overkill. C'est la contre-epreuve qui
    interdit de conclure « le regime marque toujours »."""
    r = overkill_gate_case("nocrit")
    assert r["lethal_below_threshold"], (
        "regime non atteint : degat LIVE %s vs PV %s (il faut PV <= degat < 2 x PV)"
        % (r["live_damage"], r["hp"]))
    assert not any(r["replay_crits"]), (
        "aucun coup ne devait etre critique dans ce regime : %s" % (r["replay_crits"],))
    assert r["live_overkill"] is False, (
        "le jeu a marque overkill un coup NON critique letal sous le seuil (crescendo %s -> %s) : "
        "le regime a change" % (r["live_level_before"], r["live_level_after"]))
    assert r["port_replay_overkill"] == r["live_overkill"], (
        "DESACCORD port/live sur le regime non-critique : port=%s live=%s"
        % (r["port_replay_overkill"], r["live_overkill"]))


def test_overkill_crit_pair_kills_the_hardcoded_zero(overkill_gate_case):
    """La paire crit/nocrit DOIT etre discriminante, et le corps qui passait `isCritical = 0` EN DUR
    doit y etre REFUTE : il repond « pas overkill » des DEUX cotes, alors que le live separe."""
    cr, nc = overkill_gate_case("crit"), overkill_gate_case("nocrit")
    # Les PV sont calibres sur la MEME mesure (passe 1 SANS crit) -> `base_damage` doit coincider.
    # Le degat du regime, lui, DIFFERE par construction (c'est le crit qu'on ajoute) ; ce qui doit
    # tenir des deux cotes, c'est que les deux restent letaux ET sous le seuil.
    assert cr["hp"] == nc["hp"] and cr["base_damage"] == nc["base_damage"], (
        "les deux regimes ne sont plus comparables (PV %s/%s, degat de calibration %s/%s)"
        % (cr["hp"], nc["hp"], cr["base_damage"], nc["base_damage"]))
    assert cr["lethal_below_threshold"] and nc["lethal_below_threshold"], (
        "un des deux regimes n'est plus letal-sous-le-seuil : crit degat %s / nocrit degat %s "
        "pour %s PV" % (cr["live_damage"], nc["live_damage"], cr["hp"]))
    assert cr["live_overkill"] != nc["live_overkill"], (
        "la paire n'est plus discriminante : le live rend le meme verdict avec et sans crit")
    # `legacy_overkill` = le corps 2-args pre-#178 ; `isCritical=0` en dur produit le MEME verdict.
    assert cr["legacy_overkill"] is False and nc["legacy_overkill"] is False, (
        "le corps a `isCritical = 0` devait dire « pas overkill » des DEUX cotes : %s / %s"
        % (cr["legacy_overkill"], nc["legacy_overkill"]))
    assert cr["port_replay_overkill"] is True and nc["port_replay_overkill"] is False, (
        "le corps livre doit suivre le live : crit=%s nocrit=%s"
        % (cr["port_replay_overkill"], nc["port_replay_overkill"]))


def test_overkill_crit_attributed_by_revive_gate(overkill_revive_case):
    """2e CAS DISCRIMINANT, INDEPENDANT du premier — autre observable, autre vecteur, autre tueur.

    * observable : `Narthecium_ReviveEffect` (`ultraApothecary`) revive un allie adjacent **unless
      Overkilled** (`get_ReviveOnOverkill = 0`), chance 100 -> la victime SURVIT ou non ;
    * vecteur : `On(PreUnitDeath = 1)`, pas `On(UnitDeath = 0)` du crescendo ;
    * tueur : `ultraInceptorSgt`, qui NE porte PAS le trait `ThrillSeekers` (1056). C'est ce qui
      ATTRIBUE l'observation a `isCritical` et non au rider ThrillSeekers (« defeats an enemy with
      a Crit -> always overkilled »), seul autre chemin connu vers un overkill sous le seuil."""
    cr, nc = overkill_revive_case("revive-crit"), overkill_revive_case("revive-nocrit")
    for r in (cr, nc):
        assert r["lethal_below_threshold"], (
            "regime non atteint (%s) : degat LIVE %s vs PV %s (il faut PV <= degat < 2 x PV)"
            % (r["case"], r["live_damage"], r["hp"]))
    assert cr["hp"] == nc["hp"] and cr["base_damage"] == nc["base_damage"], (
        "les deux regimes ne sont plus comparables (PV %s/%s, degat de calibration %s/%s)"
        % (cr["hp"], nc["hp"], cr["base_damage"], nc["base_damage"]))
    assert nc["live_alive"] is True, (
        "sans crit, le revive Narthecium devait rendre la victime VIVANTE (live_alive=%s) : "
        "montage casse (apothecaire hors portee ? once-per-turn deja consomme ?)" % nc["live_alive"])
    assert cr["live_alive"] is False, (
        "avec crit, l'overkill devait BLOQUER le revive (live_alive=%s) : le regime a change"
        % cr["live_alive"])
    assert nc["port_alive"] == nc["live_alive"] and cr["port_alive"] == cr["live_alive"], (
        "DESACCORD port/live sur la porte revive : crit port=%s live=%s | nocrit port=%s live=%s"
        % (cr["port_alive"], cr["live_alive"], nc["port_alive"], nc["live_alive"]))


def test_overkill_force_flag_below_threshold(overkill_revive_case):
    """`isForceOverkill` (`DealDamageInfo@+0x2c`) — 2e champ threade par #R33, mesure SANS AUCUN crit.

    `FlailSwing` (1042, `deathBlightlord`) pose `alwaysOverkilled` (`AttackOptions@+4`, 8e argument
    d'`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`) : `IsOverkill` rend vrai DES QUE
    le coup est letal, meme tres en-dessous d'`overkillDmgPctOfHealth`. Contre-epreuve = le regime
    `revive-nocrit` : MEME observable, MEME classe de degat (letal, sous le seuil, sans crit), mais
    sans le flag -> la victime est revive. Le port ne cablait `force_overkill` que sur le cap
    Resilient ; il decide AUSSI `UnitFlag.Overkilled`."""
    fl, nc = overkill_revive_case("revive-flail"), overkill_revive_case("revive-nocrit")
    # ⚠ garde-fou APPRIS A LA DURE : `aiPredict` ne rend que la preview de l'ATTAQUE NORMALE et
    # sous-estimait FlailSwing de 30 % ([9393,14091] annonces pour 20884 reels) -> tuner les PV
    # dessus donnait `dmg >= 2 x PV` = overkill NATUREL, et ce test passait SANS que le flag serve
    # a rien. Depuis #268 le degat vient d'une MESURE LIVE du vecteur sur cible increvable, et
    # c'est elle qui doit tomber dans [PV, 2 x PV).
    assert fl["lethal_below_threshold"], (
        "regime non atteint : degat LIVE %s vs PV %s (il faut PV <= degat < 2 x PV, sinon "
        "l'overkill est NATUREL et le flag n'est pas mesure)" % (fl["live_damage"], fl["hp"]))
    assert fl["is_crit_regime"] is False, "le regime FlailSwing doit etre SANS crit : %s" % fl
    assert fl["live_alive"] is False, (
        "le flag `alwaysOverkilled` devait BLOQUER le revive (live_alive=%s) : soit FlailSwing n'a "
        "pas ete cast, soit le regime a change" % fl["live_alive"])
    assert nc["live_alive"] is True, (
        "contre-epreuve cassee : sans le flag et sans crit, la victime devait etre REVIVE "
        "(live_alive=%s)" % nc["live_alive"])
    assert fl["port_alive"] == fl["live_alive"], (
        "DESACCORD port/live sur `isForceOverkill` : port_alive=%s live_alive=%s (overkill port=%s)"
        % (fl["port_alive"], fl["live_alive"], fl["port_overkill"]))
