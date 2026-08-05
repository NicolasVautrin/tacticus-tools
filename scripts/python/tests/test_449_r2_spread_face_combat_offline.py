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
     decompile, ET un zero juste qu'on retire.
  2. le DEFAUT DE SIGNATURE lui-meme (#449-r2-r5). Le point 1 seul ne suffit PAS : mesure du
     2026-08-02, changer `amount_spread_pct: int = 0` en `= 20` bascule en +-20 % les DEUX
     porteurs qui OMETTENT le mot-cle, et la premiere version de ce cliquet restait VERTE parce
     qu'elle codait ce defaut en dur au lieu de le LIRE. Le probe derive desormais le defaut, la
     position positionnelle et le gate d'activation ; ce fichier garde l'accord avec
     `EXPECTED_DEFAULT`, l'attestation lue au decompile.
  3. la NON-DEGENERESCENCE du canal. Une contre-epreuve qui tourne dans un regime ou les deux
     modeles rendent le meme nombre ne prouve rien -- c'est ainsi que la lecture `spread_pct=0`
     de la face DECISION avait << passe >> pendant des mois.
  4. le DETECTEUR lui-meme (`INV.self_test()`), qui a rendu FAUX deux de ses propres verdicts
     pendant l'ecriture de ce cliquet.

ASCII only, 100 % OFFLINE (aucun runner, aucun RPC). La confrontation LIVE correspondante est
faite par les tests des trois porteurs -- `tests/engine/runner/test_psyker_splash_live.py`,
`test_cursed_plague_bell_attack_live.py`, `test_haze_of_corruption_transfer_live.py` -- dont le
releve de contre-epreuve vit dans `docs/rl/case-449-r2-spread-face-combat.md`.
"""
from __future__ import annotations

import probe_449r2_spread_inventory as INV

from engine.services.damage_calculations import spread_to_min_max

# Montants releves LIVE pendant la contre-epreuve du 2026-08-02 (cf. la case-doc) : ce sont les
# bases sur lesquelles les trois porteurs ont reellement travaille en bataille. Ils servent ici
# a prouver que le regime mesure SEPARE les deux modeles -- pas a figer une valeur de degat.
MONTANTS_MESURES = (1506, 1795, 4860, 4164)


def _inventaire():
    defs = INV.collect_definitions(INV.ENGINE)
    INV._index_gates(INV.ENGINE, defs)
    _, sites, ambigus = INV.collect(INV.ENGINE, defs)
    actifs = [s for s in sites if not s["inert"]]
    return defs, actifs, ambigus


def test_le_detecteur_fait_ce_qu_il_dit():
    """Le garde du garde. Sur les trois derniers cliquets livres, l'auto-test a trouve un bug
    DU DETECTEUR deux fois (#440, #455) ; il en a trouve trois ici."""
    echecs = INV.self_test()
    assert not echecs, (
        "le detecteur de variance ne se comporte pas comme annonce, donc son verdict sur "
        "l'arbre ne vaut rien : %s" % (echecs,))


def test_chaque_defaut_de_variance_est_celui_qui_a_ete_LU():
    """#449-r2-r5 : c'est le DEFAUT qui porte la decision, pas seulement les call-sites.

    Deux des trois porteurs a variance nulle n'ecrivent pas le mot-cle du tout -- ils prennent
    ce defaut. Le muter les bascule en +-20 % en silence.

    #449-r2-r4 : le REGIME attendu du defaut a change. `20` n'est plus la valeur nominale, c'est
    la FAUTE -- le pct se lit dans `BattleConfiguration.Damage.DamageSpreadPercentage`.
    L'attestation porte donc sur le regime (`LU_BC` / `REQUIS`) ou, pour le seul cas ou le
    decompile impose la variance nulle, sur le litteral `0`.
    """
    defs, _, _ = _inventaire()
    assert defs, "aucune porte de variance derivee : le perimetre du probe est devenu aveugle"
    divergents = []
    for d in defs:
        att = INV.EXPECTED_DEFAULT.get(d.key)
        got = d.default if d.default_kind == "LITTERAL" else d.default_kind
        if att is None:
            divergents.append((d.file, d.line, d.call_name, d.param,
                               "NON ATTESTE (porte de variance neuve)"))
        elif got != att[0]:
            divergents.append((d.file, d.line, d.call_name, d.param,
                               "defaut LU=%s attendu=%s" % (got, att[0])))
    assert not divergents, (
        "defaut(s) de variance en desaccord avec la lecture du decompile : %s -- lire le canal "
        "de variance concerne, puis corriger le port ou inscrire la raison dans "
        "EXPECTED_DEFAULT" % (divergents,))


def test_aucune_signature_ne_reecrit_le_pct_de_la_bc():
    """#449-r2-r4 -- LE CLIQUET DU LITTERAL REVENU.

    Le natif ne connait le pct de spread QUE par sa configuration :
    `IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread` inline
    `$$get_DamageSpreadPercentageFix64`, qui lit `configuration+0x20` -- la signature native n'a
    AUCUN parametre de spread. Un defaut entier NON NUL dans une signature du port est donc un
    couplage non lu, muet le jour ou la BC vaut autre chose.

    Ce n'est pas theorique : MESURE du 2026-08-05 (`probe_449r2r4_spread_from_bc`), meme seed,
    meme board, memes unites, seule la section `BC.Damage` change --

        DamageSpreadPercentage = 20 -> le natif inflige 9388, le port aussi
        DamageSpreadPercentage = 60 -> le natif inflige 7774, un port a 20 en dur calcule 9388
        champ ABSENT                -> le natif inflige 8434 (spread 0), le port a 20 : 9388
        IgnoreDamageSpread = true   -> le natif inflige 8434 (spread 0), le port a 20 : 9388

    Le seul entier legitime est `0`, et seulement la ou le decompile impose la variance nulle
    (mode `amount`, `Nullable<AttackDamageBehaviourOptions>` VIDE).
    """
    defs, _, _ = _inventaire()
    ecrits = [(d.file, d.line, d.call_name, d.param, d.default) for d in defs
              if d.default_kind == "LITTERAL" and d.default != 0]
    assert not ecrits, (
        "signature(s) qui REECRIVENT le pct de spread au lieu de le lire dans la BC : %s -- "
        "regime attendu `= None` (foyer `engine.services.damage_config.resolve_spread_pct`)"
        % (ecrits,))


def test_le_foyer_lit_la_bc_puis_la_seed_versionnee():
    """Le foyer resout dans l'ORDRE annonce, et son defaut est DERIVE -- pas ecrit.

    Ordre natif mirroré : une valeur explicite l'emporte (l'appelant a lu SON decompile) ; sinon
    la BC de cette bataille (`State`, pose par `load_state(damage_config=...)`) ; sinon le defaut
    LU dans `data/seed-bc.json`. `IgnoreDamageSpread` (`configuration+0x31`, lu par
    `IdunBattle.Core.Services.DamagePrediction$$get_IgnoreDamageSpread`) court-circuite a 0 --
    CONFRONTE LIVE : bras `ignore`, natif 8434 = bornes plates.
    """
    from engine.services.damage_config import (resolve_spread_pct, seed_damage_section,
                                               default_damage_spread_percentage,
                                               DamageConfiguration)
    from engine.runner.state import State

    seed_pct = seed_damage_section().get("DamageSpreadPercentage")
    assert seed_pct is not None, (
        "`data/seed-bc.json` n'a plus `Damage.DamageSpreadPercentage` : le defaut du port EST "
        "cette valeur (il n'est ecrit nulle part), il n'a donc plus de source")
    assert default_damage_spread_percentage() == int(seed_pct)

    st = State()
    assert resolve_spread_pct(None, st) == int(seed_pct), "canal absent -> defaut derive"
    assert resolve_spread_pct(0, st) == 0, "une valeur explicite prime toujours"

    cfg = DamageConfiguration.from_bc({"DamageSpreadPercentage": 60})
    st.damage_spread_percentage = cfg.damage_spread_percentage
    assert resolve_spread_pct(None, st) == 60, "la BC de la bataille prime sur le defaut"
    assert resolve_spread_pct(7, st) == 7, "une valeur explicite prime sur la BC"

    st.ignore_damage_spread = True
    assert resolve_spread_pct(None, st) == 0, "IgnoreDamageSpread -> branche plate"
    assert resolve_spread_pct(7, st) == 7, (
        "IgnoreDamageSpread ne doit PAS ecraser une valeur explicite : les porteurs a variance "
        "nulle/imposee ont lu leur propre decompile (#449-r2)")

    # Champ ABSENT de la section fournie == 0, comme le natif : le ctor
    # `IdunBattle.Configuration.DamageConfiguration$$.ctor` n'initialise QUE `DamageProfiles`,
    # donc rien ne fabrique 20 cote jeu non plus (CONFRONTE : bras `absent`, natif 8434).
    assert DamageConfiguration.from_bc({}).damage_spread_percentage == 0
    assert DamageConfiguration.from_bc(None) is None, "canal non fourni != zero mesure"


def test_le_cablage_de_bout_en_bout_suit_la_bc():
    """Le canal REEL : `BC.Damage` -> `load_state` -> `State` -> `Runner` -> `DamageHandler`.

    C'est ce chemin-la qui portait le littéral (`install_default_handlers`, `DamageHandler`), et
    c'est lui que la mesure live a chiffre. Un `State` nu (aucune BC connue) retombe sur le
    defaut derive de la seed -- comportement STRICTEMENT inchange pour tout appelant existant.
    """
    from engine.runner.state import State
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state
    from engine.services.damage_config import default_damage_spread_percentage

    nu = Runner(State()).install_default_handlers().damage_handler.spread_pct
    assert nu == default_damage_spread_percentage()

    vide = {"units": [], "currentPlayer": None}
    for pct in (0, 5, 60, 100):
        st = load_state(vide, {}, damage_config={"DamageSpreadPercentage": pct})
        got = Runner(st).install_default_handlers().damage_handler.spread_pct
        assert got == pct, "BC.pct=%d -> DamageHandler.spread_pct=%d" % (pct, got)

    st = load_state(vide, {}, damage_config={"DamageSpreadPercentage": 60,
                                             "IgnoreDamageSpread": True})
    assert Runner(st).install_default_handlers().damage_handler.spread_pct == 0


def test_aucun_parametre_de_variance_n_est_mort():
    """Un parametre accepte et JAMAIS LU est un no-op silencieux : la variance cesse d'etre
    appliquee et tout call-site qui la passe devient decoratif."""
    defs, _, _ = _inventaire()
    morts = [(d.file, d.line, d.call_name, d.param) for d in defs if d.reads == 0]
    assert not morts, ("parametre(s) de variance accepte(s) mais lu(s) nulle part : %s"
                       % (morts,))


def test_inventaire_des_sites_a_variance_nulle_est_justifie():
    """Sens 1 : tout call-site ACTIF a variance NULLE porte sa raison LUE au decompile."""
    _, actifs, _ = _inventaire()
    zero = [s for s in actifs
            if not s.get("from_bc") and not s["dynamic"] and not s["unresolved"]
            and int(s["value"]) == 0]
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
    _, actifs, _ = _inventaire()
    par_site = {}
    for s in actifs:
        par_site.setdefault((s["file"], s["callee"]), []).append(s)
    regressions = []
    for key in INV.EXPECTED_ZERO:
        for s in par_site.get(key, []):
            if s.get("from_bc") or s["dynamic"] or s["unresolved"] or int(s["value"]) != 0:
                regressions.append((s["file"], s["line"], s["callee"],
                                    "dyn" if s["dynamic"] else s["value"]))
    assert not regressions, (
        "site(s) dont le decompile impose une variance NULLE et qui ne l'ont plus : %s -- "
        "le natif y passe le Nullable<AttackDamageBehaviourOptions> VIDE" % (regressions,))


def test_chaque_justification_designe_un_site_reel():
    """Une justification qui ne designe plus rien est une garde qui a survecu a son gisement."""
    defs, actifs, _ = _inventaire()
    vus = {(s["file"], s["callee"]) for s in actifs}
    perimes = [k for k in INV.EXPECTED_ZERO if k not in vus]
    assert not perimes, ("entree(s) de EXPECTED_ZERO sans call-site actif correspondant : %s"
                         % (perimes,))
    cles = {d.key for d in defs}
    perimes_def = [k for k in INV.EXPECTED_DEFAULT if k not in cles]
    assert not perimes_def, (
        "entree(s) de EXPECTED_DEFAULT sans signature correspondante : %s" % (perimes_def,))


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
