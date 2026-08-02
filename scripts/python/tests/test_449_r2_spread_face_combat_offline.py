"""#449-r2 -- CLIQUET de la variance d'arme sur le SLOT DE MONTANT, face COMBAT.

#449 a etabli que, cote PREDICTION, le slot de montant APPLIQUE le spread +-20 % : les trois
surcharges de `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` ecrivent le
byte d'aiguillage `DamagePredictionRequest+0x6a` a `1` EN DUR.

Cote COMBAT le meme byte existe et pilote le meme embranchement, mais il n'est PAS constant :
il vient des OPTIONS du behaviour. La chaine, lue de bout en bout sur le build `rnca9r7q6c` :

    <Ability>$$CreateBehaviour            8e arg = Nullable<AttackDamageBehaviourOptions>
      -> IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor
             Nullable<T>.GetValueOrDefault -> les 0x28 octets atterrissent a `this+0x98`,
             donc l'octet d'aiguillage (options+6) EST `behaviour+0x9e`
      -> IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget
             options+0x2f <- behaviour+0x9e
      -> IdunBattle.Operations.AttackDamageOperation$$ExecuteHit
             request+0x6a <- options+0x2f
      -> IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw
             request+0x6a == 0 -> MinMaxDamageFix64(d, maxOverride ?? d)     [PLAT]
             sinon             -> DamagePrediction$$GetBaseDamageFix64       [SPREAD +-20 %]

=> la conclusion de #449 NE SE TRANSPORTE PAS : un `amount_spread_pct=0` de la face COMBAT est
JUSTE des lors que son `CreateBehaviour` passe le Nullable VIDE. Contre-preuve LUE, qui interdit
de generaliser dans l'autre sens :
`IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` pose cet
octet a **1** en dur (seul octet non nul de la struct), et le port lui donne bien 20.

CE QUE CE CLIQUET GARDE, et que rien d'autre ne voit :

  1. l'INVENTAIRE (`probe_449r2_spread_inventory`), dans les DEUX sens -- un zero non justifie au
     decompile, ET un zero juste qu'on retire. Le second sens n'est pas cosmetique : sans lui, le
     mutant `amount_spread_pct=20` pose sur les trois porteurs laissait le probe VERT (plus aucun
     zero a justifier). C'est la forme exacte du trou nomme en #449 §8.
  2. la NON-DEGENERESCENCE du canal. Une contre-epreuve qui tourne dans un regime ou les deux
     modeles rendent le meme nombre ne prouve rien -- c'est ainsi que la lecture `spread_pct=0`
     de la face DECISION avait « passe » pendant des mois. On atteste donc que sur les montants
     REELLEMENT mesures en bataille, le modele plat et le modele +-20 % sont SEPARES.

ASCII only, 100 % OFFLINE (aucun runner, aucun RPC). La confrontation LIVE correspondante est
faite par les tests des trois porteurs -- `tests/engine/runner/test_psyker_splash_live.py`,
`test_cursed_plague_bell_attack_live.py`, `test_haze_of_corruption_transfer_live.py` -- dont le
relevé de contre-epreuve vit dans `docs/rl/case-449-r2-spread-face-combat.md`.
"""
from __future__ import annotations

import probe_449r2_spread_inventory as INV

from engine.services.damage_calculations import spread_to_min_max

# Montants relevés LIVE pendant la contre-épreuve du 2026-08-02 (cf. la case-doc) : ce sont les
# bases sur lesquelles les trois porteurs ont réellement travaillé en bataille. Ils servent ici
# à prouver que le régime mesuré SEPARE les deux modèles -- pas à figer une valeur de dégât.
MONTANTS_MESURES = (1506, 1795, 4860, 4164)


def test_inventaire_des_sites_a_variance_nulle_est_justifie():
    """Sens 1 : tout site a variance NULLE porte sa raison LUE au decompile."""
    amount_sites, nl_sites, foyer_sites = INV.collect(INV.ENGINE)
    zero = [s for s in amount_sites + nl_sites + foyer_sites
            if not s["dynamic"] and int(s["value"]) == 0]
    assert zero, ("aucun site a variance nulle : le gisement de ce cliquet a disparu, "
                  "ce qui invalide sa raison d'etre -- re-lire la case-doc avant de le retirer")
    orphelins = [(s["file"], s["line"], s["callee"]) for s in zero
                 if (s["file"], s["callee"]) not in INV.EXPECTED_ZERO]
    assert not orphelins, (
        "site(s) a variance nulle SANS justification lue au decompile : %s -- "
        "lire le 8e argument Nullable<AttackDamageBehaviourOptions> du CreateBehaviour natif, "
        "puis inscrire la raison dans EXPECTED_ZERO (ou corriger le port)" % (orphelins,))


def test_les_sites_lus_au_decompile_sont_toujours_a_zero():
    """Sens 2 : un zero JUSTE qu'on retire doit faire rougir (c'est ce qui manquait a #449)."""
    amount_sites, nl_sites, foyer_sites = INV.collect(INV.ENGINE)
    par_site = {}
    for s in amount_sites + nl_sites + foyer_sites:
        par_site.setdefault((s["file"], s["callee"]), []).append(s)
    regressions = []
    for key in INV.EXPECTED_ZERO:
        for s in par_site.get(key, []):
            if s["dynamic"] or int(s["value"]) != 0:
                regressions.append((s["file"], s["line"], s["callee"],
                                    "dyn" if s["dynamic"] else s["value"]))
    assert not regressions, (
        "site(s) dont le decompile impose une variance NULLE et qui ne l'ont plus : %s -- "
        "le natif y passe le Nullable<AttackDamageBehaviourOptions> VIDE" % (regressions,))


def test_chaque_justification_designe_un_site_reel():
    """Une justification qui ne designe plus rien est une garde qui a survecu a son gisement."""
    amount_sites, nl_sites, foyer_sites = INV.collect(INV.ENGINE)
    vus = {(s["file"], s["callee"]) for s in amount_sites + nl_sites + foyer_sites}
    perimes = [k for k in INV.EXPECTED_ZERO if k not in vus]
    assert not perimes, ("entree(s) de EXPECTED_ZERO sans site correspondant : %s" % (perimes,))


def test_le_canal_separe_les_deux_modeles_sur_les_montants_mesures():
    """NON-DEGENERESCENCE : sans elle, la contre-epreuve live ne prouverait rien.

    Le piege que #449 a documente : un accord obtenu sur un canal qui ne PEUT PAS exprimer la
    difference n'est pas une validation faible, c'est un non-evenement. On verifie donc que sur
    les montants reellement rencontres en bataille, le modele PLAT (min == max == d) et le
    modele +-20 % sont strictement separes -- donc qu'un port errone y serait VISIBLE.
    """
    for base in MONTANTS_MESURES:
        plat = spread_to_min_max(base, 0)
        etale = spread_to_min_max(base, 20)
        assert plat.min == plat.max == base, (
            "spread 0 doit rendre des bornes DEGENEREES (le natif y fait "
            "MinMaxDamageFix64(d, d)) ; base=%s -> (%s, %s)" % (base, plat.min, plat.max))
        assert etale.min < base < etale.max, (
            "spread 20 doit ENCADRER strictement la base, sinon le regime est degenere et "
            "la contre-epreuve ne discrimine rien ; base=%s -> (%s, %s)"
            % (base, etale.min, etale.max))
