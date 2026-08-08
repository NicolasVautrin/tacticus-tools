"""CONFRONT LIVE de `1164 MindControl` (`genesMagus` << Magus >>, Genestealer Cults, HERO) -- #552.

Ce que ce fichier GARDE, et pourquoi chaque garde existe :

  * **le cast NE FRAPPE PAS -- ET NE TIRE RIEN.** L'audit `docs/rl/combat-ability-coverage.md`
    classe 1164 `EFFECT/BUFF` ; cette colonne derive du `damageProfile` de l'ARME du porteur, pas
    du behaviour, donc elle ne PROUVE rien. Le critere n'est pas << 0 degat observe >> mais
    << 0 degat ET flux MT STRICTEMENT identique >> : un jet de crit ou de block CONSOMME un tirage
    (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`), donc un MT fige PROUVE que le
    canal degat est hors de ce behaviour.
  * **CE N'EST PAS UN OWNER-SWAP.** Le nom le suggere ; l'arbre ne touche ni l'appartenance
    d'equipe ni l'ordre d'activation. La garde lit l'EQUIPE de la cible avant/apres.
  * **l'empreinte D'EFFETS et les BONDS.** 1349 / 1350 sur la CIBLE ; 27
    `Taunted_OnlySpecificTargets` (COMPOSITE : `TauntedEffect$$ApplyInternal` spawne 25/26/1237)
    sur la CIBLE et BONDE au TAUNTEUR ; 1367 `MindControl_Taunter` sur le TAUNTEUR et BONDE a la
    CIBLE. Le bond n'est pas visible dans `decisionView.effects` -> la garde lit la CASCADE du
    cast natif.
  * **LE DISCRIMINANT DU TAUNTEUR.** `Cache(First(SortByFormula(Attackable(Friends(Owner,
    AdjacentUnits(Target))), StatAmount(It, HEALTH), ascending = 0), 1))` = l'allie du CASTER,
    adjacent a la cible, a la plus haute Health COURANTE. Le montage rend TROIS lectures fausses
    distinguables : l'allie a la plus BASSE Health est le PREMIER voisin enumere, donc
    << premier >> et << plus basse >> designent tous deux l'AUTRE unite. Inverser le flag
    `ascending` (un seul octet du decompile) fait rougir cette garde.
  * **les DEUX debuffs MORDENT, ils ne sont pas que POSES** : la prediction NATIVE de l'attaque de
    la cible BAISSE (1349, `ForAddition(get_OwnerIsCaster, Negative(ConfigVar dmgReduction))`) et
    celle d'un allie SUR la cible MONTE (1350, `ForPercentIncrease(get_OwnerIsTarget,
    ConfigVar extraDmgPct)`). Les DEUX SENS sont exiges : un port qui aurait interverti les deux
    effets passerait un test a un seul sens.
  * **le TAUNT est OPPOSABLE** : l'ennemi mind-controle ne peut plus viser que le taunteur
    (`UnitExtensions$$GetOnlyTargets` -> `TargetIsAllowedForCaster`), port ET natif.
  * **le GATE DE CIBLAGE et la REGLE DYNAMIQUE.** `TARGETING_OPTIONS` absent =>
    `get_invalid_target_reason` rend 0 immediatement (degradation PERMISSIVE, invisible en
    self-play). Le masque de 1164 a MIGRE ici depuis `TARGETING_OPTIONS_UNPORTED` (contrat de
    DISJONCTION) -- ce test verifie AUSSI qu'il n'y est plus. Et la regle dynamique
    (`GetAdjacentUnits(targetTiles, friendsOf = caster)` non vide) est NEUVE : avant #552 le port
    rendait `0` sur un ennemi sans aucun allie adjacent, la ou le natif refuse.
  * **la face DECISION.** Un accord COMBAT ne dit RIEN de la DECISION : `MindControlPlaybook`
    choisit la CIBLE par `Fix64(GetStat(cible, HEALTH))`. La garde confronte la proposition de
    l'IA NATIVE (`aiDryRunAllUnits`, read-only) a celle du port sur DEUX ennemis legaux aux PV
    tres differents -- l'ennemi FAIBLE etant le PREMIER enumere.

Le montage (build + DRIVE des positions par `--place`/`--a-place` + craft de PV par `--unit-stat`)
et TOUTES les lectures vivent dans `scripts/python/probe_552_mind_control.py` : le probe MESURE,
ce test GARDE, une seule implementation -- aucune divergence possible entre les deux.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_552_mind_control as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est une MESURE, pas une facilite : ce fichier importe le PROBE, qui
    # importe `ABILITY_CLASSES` et `engine_validate` -- sa fermeture d'import atteint la
    # quasi-totalite de `scripts/python`. Declarer etroit produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    # Le NATIF est l'oracle de TOUTES ces gardes : un changement de build peut les faire changer
    # d'avis sans qu'une ligne du port bouge.
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de 1164, faces COMBAT ET DECISION. Le verdict "
              "depend du code du port (arbre DSL + AddEffect/AddBondEffect + les selecteurs "
              "AdjacentUnits/Friends/Attackable/SortByFormula/First/Cache + StatAmount + les trois "
              "effets MindControl_* + TauntedEffect + le registre + le masque + la regle dynamique "
              "+ le playbook), du MONTAGE (le probe, qui porte le drive des positions, le craft de "
              "PV et TOUTES les lectures), des entrees versionnees du runner, et du BUILD charge "
              "-- l'oracle etant le jeu lui-meme, pas une constante ecrite ici.",
}

MIND_CONTROL = P.MIND_CONTROL              # 1164 ActiveAbilityType.MindControl
OUT_DMG_REDUCTION = P.OUT_DMG_REDUCTION    # 1349 EffectType.MindControl_OutoingDamageReduction
IN_DMG_BONUS = P.IN_DMG_BONUS              # 1350 EffectType.MindControl_IncomingDamageBonus
TAUNTED = P.TAUNTED                        # 27   EffectType.Taunted_OnlySpecificTargets
TAUNTER = P.TAUNTER                        # 1367 EffectType.MindControl_Taunter


def _target_is_allowed_for_caster() -> int:
    """`TargetingRule` bit 23 -- le code que rend la cascade quand le TAUNT refuse une cible. Pris
    au MEMBRE du mirror genere, jamais au litteral : un ordinal juste aujourd'hui devient faux au
    changement de build, en silence."""
    from engine.runner.abilities.targeting_rule import TargetingRule
    return int(TargetingRule.TargetIsAllowedForCaster)


def _target_matches_dynamic_rule() -> int:
    from engine.runner.abilities.targeting_rule import TargetingRule
    return int(TargetingRule.TargetMatchesDynamicRule)


def _target_is_enemy() -> int:
    from engine.runner.abilities.targeting_rule import TargetingRule
    return int(TargetingRule.TargetIsEnemy)


@pytest.fixture(scope="module")
def mc(live_session):
    """UN SEUL runner pour la face COMBAT : le cast est joue une fois des DEUX cotes, les gardes
    ci-dessous relisent la MEME mesure (le cast n'est pas rejouable -- il consomme l'actif)."""
    m, dispose = P.measure(live_session, state_name="test_552_mind_control")
    try:
        yield m
    finally:
        dispose()


@pytest.fixture(scope="module")
def mc_dec(live_session):
    """Montage SEPARE pour la face DECISION : deux ennemis LEGAUX aux PV tres differents."""
    d, dispose = P.measure_decision(live_session, state_name="test_552_mind_control_dec")
    try:
        yield d
    finally:
        dispose()


def test_mind_control_execution_is_ported(mc):
    """La face EXECUTION est portee : sans elle, la DECISION choisit le cast et l'EXECUTION
    l'IGNORE -- 0 debuff, 0 taunt, AUCUNE erreur (le no-op silencieux que #552 ferme)."""
    assert mc["routed"] == "handler" and mc["ported"] is True, \
        "1164 non portee (routed=%s ported=%s)" % (mc["routed"], mc["ported"])
    assert not mc["cast_error"], "cast natif bloque: %s" % mc["cast_error"]
    assert mc["mutated"] is True, "le cast natif n'a MUTE rien du tout (mutated=%s)" % mc["mutated"]


def test_mind_control_effect_footprint_matches_native(mc):
    """Empreinte `{unite -> {effectType: remaining}}` : le port doit poser EXACTEMENT les effets du
    natif, sur les MEMES porteurs, avec les MEMES durees.

    Les QUATRE poses partagent `TurnsFromRounds(2)` (litteral `2` du decompile, PAS un
    `GetNumberConstant` : `MindControl.constants` ne porte que `range`) ; les trois sous-effets du
    taunt heritent la duree du parent (`AddSubEffectWithSameTurns`)."""
    off, live = mc["off"], mc["live"]
    assert off == live, "empreinte d'effets offline %s != live %s" % (off, live)
    cible, taunteur, faible = mc["target"], mc["high"], mc["low"]
    assert {OUT_DMG_REDUCTION, IN_DMG_BONUS, TAUNTED} <= set(off.get(cible, {})), \
        "la CIBLE u%d porte %s, attendu au moins {1349, 1350, 27}" % (cible, off.get(cible))
    assert set(off.get(taunteur, {})) == {TAUNTER}, \
        "le TAUNTEUR u%d porte %s, attendu exactement {1367}" % (taunteur, off.get(taunteur))
    assert faible not in off, \
        "l'allie NON retenu u%d a recu quelque chose (%s) -- un seul taunteur est designe " \
        "(`First(..., 1)`)" % (faible, off.get(faible))
    durees = set(off[cible].values()) | set(off[taunteur].values())
    assert len(durees) == 1 and durees.pop() > 0, \
        "les quatre poses partagent `TurnsFromRounds(2)` -- durees mesurees %s / %s" % (
            off[cible], off[taunteur])


def test_mind_control_taunter_is_the_highest_health_ally(mc):
    """LE DISCRIMINANT. Le taunteur est l'allie du CASTER, adjacent a la cible, a la plus haute
    Health COURANTE -- et le montage le distingue de DEUX lectures fausses :

      * << le PREMIER voisin enumere >> : l'allie FAIBLE est en `(2,4)`, 2e voisin de la cible dans
        l'ordre de l'adjacence stockee ; le FORT est en `(4,4)`, le DERNIER ;
      * << la plus BASSE Health >> : c'est exactement l'allie FAIBLE.

    Inverser le flag `ascending` de `SortByFormula` (un seul octet du decompile) rend donc cette
    garde ROUGE, et elle seule -- l'empreinte d'effets, elle, ne changerait que de PORTEUR."""
    off, live = mc["off"], mc["live"]
    hp = mc["hp_allies"]
    assert hp["high"] > hp["low"], \
        "REGIME DEGENERE : les deux allies ont la meme Health (%s) -- le tri ne discrimine RIEN" % (
            hp,)
    for cote, src in (("port", off), ("natif", live)):
        assert TAUNTER in (src.get(mc["high"]) or {}), \
            "%s : 1367 n'est PAS sur l'allie a la plus HAUTE Health (u%d) -- porteurs vus %s" % (
                cote, mc["high"], sorted(src))
        assert TAUNTER not in (src.get(mc["low"]) or {}), \
            "%s : 1367 est sur l'allie a la plus BASSE Health (u%d) -- le tri est INVERSE" % (
                cote, mc["low"])


def test_mind_control_bonds_pair_target_and_taunter(mc):
    """Les 5es arguments natifs des DEUX `AddBondEffect` sont CROISES :

        AddBondEffect(27,   ..., targets = Target, bondedEntity = cache)
        AddBondEffect(1367, ..., targets = cache,  bondedEntity = Target)

    C'est l'etage que l'empreinte ne voit pas (`decisionView.effects` ne publie pas le bond) et le
    seul qui rende le taunt OPPOSABLE : `TauntedEffect$$ApplyInternal` ecrit
    `ForcedAttackTargetsComponent.<+0x50> = [BondedEntityId]`. Un bond nul laisserait le builder
    ORDINAIRE (aucun bond) et le taunt serait un effet INERTE. Intervertir les deux bonds fait
    rougir CETTE garde."""
    cible, taunteur = mc["target"], mc["high"]
    for cote, src in (("port", mc["off_bonds"]), ("natif", mc["live_bonds"])):
        assert src, "%s : aucun bond publie -- l'oracle est MUET, l'accord ne peut pas etre " \
                    "confirme (canal a re-verifier)" % cote
        taunt = sorted((int(x["on"]), x["bonded"]) for x in (src.get(TAUNTED) or []))
        assert taunt == [(cible, taunteur)], \
            "%s : 27 pose/bonde %s, attendu [(%d, %d)]" % (cote, taunt, cible, taunteur)
        marque = sorted((int(x["on"]), x["bonded"]) for x in (src.get(TAUNTER) or []))
        assert marque == [(taunteur, cible)], \
            "%s : 1367 pose/bonde %s, attendu [(%d, %d)]" % (cote, marque, taunteur, cible)
        for et in (OUT_DMG_REDUCTION, IN_DMG_BONUS):
            plats = [(int(x["on"]), x["bonded"]) for x in (src.get(et) or [])]
            assert plats == [(cible, None)], \
                "%s : %d doit etre un AddEffect NON bonde sur la cible, vu %s" % (cote, et, plats)


def test_mind_control_cast_deals_no_damage_and_draws_nothing(mc):
    """LA REPONSE A `Q1` -- la categorie `EFFECT/BUFF` de l'audit est-elle JUSTE ?

    Le flux MT fige (`dumpRng` cote natif, `call_count` cote port sur un MT CALE sur le live) est
    ce qui transforme << aucun degat observe >> en << canal degat INATTEIGNABLE >> : un jet de crit
    ou de block en consommerait un.

    ⚠ La comparaison porte sur les UNITES du montage : le cast CREE des entites-effet, qui
    apparaissent des deux cotes avec un `HealthComponent` a 0/1 -- ce ne sont pas des PV
    d'unite."""
    unites = (mc["caster"], mc["low"], mc["high"], mc["target"], mc["lone"])
    for cote, (before, after) in (("port", mc["off_hp"]), ("natif", mc["live_hp"])):
        changes = {k: (before.get(k), after.get(k)) for k in unites
                   if after.get(k) != before.get(k)}
        assert not changes, "%s : le CAST a change des HP %s -- il ne doit RIEN infliger" % (
            cote, changes)
    off0, off1 = mc["rng_off"]
    assert off0 is not None and off0 == off1, \
        "port : le MT a avance (%s -> %s) -- le cast ne doit consommer AUCUN tirage" % (off0, off1)
    live0, live1 = mc["rng_live"]
    assert live0[0] is not None, "natif : `dumpRng` muet -- le MT n'est PAS mesure (pas un vert)"
    assert live0 == live1, \
        "natif : le MT a avance (%s -> %s) -- le cast ne doit consommer AUCUN tirage" % (
            live0, live1)


def test_mind_control_is_not_an_owner_swap(mc):
    """LA REPONSE A `Q2`. Le NOM suggere une prise de controle ; l'arbre ne porte AUCUN noeud
    d'appartenance d'equipe ni d'activation. La cible reste dans SON camp -- ce qui change, c'est
    la liste de ses cibles legales (garde suivante)."""
    assert mc["team_target_before"] is not None, \
        "l'equipe de la cible n'est PAS mesuree -- pas un vert"
    assert mc["team_target_after"] == mc["team_target_before"], \
        "l'equipe de la cible a CHANGE (%s -> %s) : ce serait un owner-swap, pas un taunt" % (
            mc["team_target_before"], mc["team_target_after"])


def test_mind_control_taunt_restricts_the_target_to_its_taunter(mc):
    """GENERALISATION : le taunt est-il OPPOSABLE ?

    Deux lectures INDEPENDANTES du meme fait :
      * cote port, `UnitExtensions$$GetOnlyTargets` rend `[taunteur]` pour la cible, `[]` pour
        l'ennemi TEMOIN non taunte ;
      * cote natif, la matrice `abilityReason(<cible>, NormalAttack, <unite du joueur>)` BASCULE :
        l'allie FAIBLE sort des cibles legales (bit 23 `TargetIsAllowedForCaster`) alors qu'il
        etait ACCEPTE avant le cast, et le taunteur reste accepte.

    ANTI-DEGENERESCENCE : au moins UNE bascule doit partir d'une cible ACCEPTEE (0), sinon on ne
    mesurerait qu'un changement de LIBELLE de refus."""
    bit = _target_is_allowed_for_caster()
    cible, taunteur, faible = mc["target"], mc["high"], mc["low"]
    assert mc["off_only"].get(cible) == [taunteur], \
        "port : GetOnlyTargets(u%d) = %s, attendu [%d]" % (
            cible, mc["off_only"].get(cible), taunteur)
    assert mc["off_only"].get(mc["lone"]) == [], \
        "port : l'ennemi TEMOIN u%d est restreint (%s) -- il ne doit pas l'etre" % (
            mc["lone"], mc["off_only"].get(mc["lone"]))
    av, ap, op = mc["matrice_before"], mc["matrice_after"], mc["off_matrice"]
    assert ap == op, "la matrice de gate diverge port/natif : natif=%s port=%s" % (ap, op)
    assert av[(cible, faible)] == 0, \
        "REGIME DEGENERE : l'allie FAIBLE n'etait DEJA pas une cible legale (%s) -- la bascule ne " \
        "prouverait rien" % hex(av[(cible, faible)])
    assert ap[(cible, faible)] & bit, \
        "l'allie FAIBLE reste attaquable par la cible tauntee (%s) -- le taunt ne mord pas" % hex(
            ap[(cible, faible)])
    assert ap[(cible, taunteur)] == 0, \
        "le TAUNTEUR n'est plus attaquable par la cible (%s) -- le bond designe la mauvaise " \
        "unite" % hex(ap[(cible, taunteur)])


def test_mind_control_debuffs_bite_in_both_directions(mc):
    """GENERALISATION : les deux debuffs sont-ils VIVANTS, ou seulement presents ? ET dans le BON
    SENS chacun ?

    * `1349` (`ForAddition(get_OwnerIsCaster, Negative(ConfigVar 0x12 = dmgReduction))`) : la
      prediction NATIVE de l'attaque de la CIBLE doit BAISSER.
    * `1350` (`ForPercentIncrease(get_OwnerIsTarget, ConfigVar 0xa = extraDmgPct)`) : la prediction
      NATIVE d'une attaque SUR la cible doit MONTER.

    Exiger les DEUX SENS est ce qui interdit d'intervertir les deux classes d'effet : un port qui
    les echangerait ferait baisser ce qui doit monter.

    ⚠ ON NE RECONSTITUE PAS L'ARITHMETIQUE NATIVE (arrondis Fix64 par coup, ordre des accumulateurs)
    -- le critere est le SENS, et le canal (additif PLAT contre POURCENT) est verifie separement
    sur les `EffectBonus` que le port RENDS. ANTI-DEGENERESCENCE : les deux magnitudes de config
    doivent etre NON NULLES.

    ⚠ ET LE SENS NATIF EST CONFRONTE AU SIGNE DU PORT. Sans ce dernier bloc, cette garde ne lirait
    que l'ORACLE : aucune mutation du port ne pourrait la faire rougir, et << une garde jamais vue
    rouge ne garde rien >>. C'est le couplage des deux cotes qui en fait une garde de PORT et pas
    seulement un cliquet de RE."""
    assert mc["dmg_reduction"] and int(mc["dmg_reduction"]) > 0, \
        "REGIME DEGENERE : dmgReduction=%s" % mc["dmg_reduction"]
    assert mc["extra_dmg_pct"] and int(mc["extra_dmg_pct"]) > 0, \
        "REGIME DEGENERE : extraDmgPct=%s" % mc["extra_dmg_pct"]
    ob, oa = mc["pred_out"]
    ib, ia = mc["pred_in"]
    assert ob and oa and ib and ia, \
        "prediction native absente (sortante %s -> %s ; entrante %s -> %s)" % (ob, oa, ib, ia)
    assert all(y < x for x, y in zip(ob, oa)), \
        "1349 ne mord pas : la prediction SORTANTE de la cible passe de %s a %s (attendu BAISSE " \
        "de %s plat)" % (ob, oa, mc["dmg_reduction"])
    assert all(y > x for x, y in zip(ib, ia)), \
        "1350 ne mord pas : la prediction ENTRANTE sur la cible passe de %s a %s (attendu HAUSSE " \
        "de %s %%)" % (ib, ia, mc["extra_dmg_pct"])
    # COUPLAGE PORT <-> NATIF : le SIGNE que rend le port doit aller dans le sens que le natif
    # MESURE. C'est ce qui rend cette garde sensible a une mutation du PORT.
    out = mc["off_bonus"].get(OUT_DMG_REDUCTION) or {}
    inc = mc["off_bonus"].get(IN_DMG_BONUS) or {}
    assert (out.get("value") or 0) < 0, \
        "le natif fait BAISSER la prediction sortante mais le port rend %s pour 1349" % out
    assert (inc.get("value") or 0) > 0 and inc.get("kind") == "PercentIncrease", \
        "le natif fait MONTER la prediction entrante mais le port rend %s pour 1350" % inc


def test_mind_control_effect_bonuses_have_the_right_kind_sign_and_face(mc):
    """Le CANAL de chaque debuff, lu sur l'instance MATERIALISEE cote port -- ce que la prediction
    native, scalaire, ne peut pas separer :

    * `1349` : `Addition` NEGATIF, `owner_is_caster = True` (le porteur ATTAQUE), face `attacker`.
    * `1350` : `PercentIncrease` POSITIF, `owner_is_caster = False` (le porteur DEFEND), face
      `attacker` AUSSI -- la classe native derive de `BaseEffect` et declare
      `CreateEffectDamageBonusForAttack` (slot 0x16), donc le natif verse sa contribution dans
      `attackModifiers` MALGRE son trigger `get_OwnerIsTarget` (#437-r1-r1-r1). Rabattre cette face
      sur << qui PORTE l'effet >> a deja coute un `-1` (#586).

    Les MAGNITUDES sont celles du gameconfig au niveau/multiplicateur du CASTER : elles ne sont pas
    ecrites ici, elles sont RE-DERIVEES par le probe (`ability_var`)."""
    b = mc["off_bonus"]
    out = b.get(OUT_DMG_REDUCTION) or {}
    inc = b.get(IN_DMG_BONUS) or {}
    assert out.get("kind") == "Addition" and out.get("owner_is_caster") is True, \
        "1349 : canal/kind/owner faux -> %s" % out
    assert out.get("value") == -int(mc["dmg_reduction"]), \
        "1349 : montant %s, attendu -%s (Negative(ConfigVar dmgReduction))" % (
            out.get("value"), mc["dmg_reduction"])
    assert out.get("native_face") == "attacker", "1349 : face native %s" % out.get("native_face")
    assert inc.get("kind") == "PercentIncrease" and inc.get("owner_is_caster") is False, \
        "1350 : canal/kind/owner faux -> %s" % inc
    assert inc.get("value") == int(mc["extra_dmg_pct"]), \
        "1350 : montant %s, attendu %s (ConfigVar extraDmgPct)" % (
            inc.get("value"), mc["extra_dmg_pct"])
    assert inc.get("native_face") == "attacker", \
        "1350 : face native %s -- la classe native declare CreateEffectDamageBonusForAttack " \
        "(slot 0x16), donc l'accumulateur ATTAQUANT" % inc.get("native_face")


def test_mind_control_targeting_gate_and_dynamic_rule_match_the_native(mc):
    """Le masque `0x4002` (`TargetMatchesDynamicRule | TargetIsEnemy`) ET la regle dynamique NEUVE,
    confrontes sur QUATRE sondes : soi / un allie / la cible / un ennemi TEMOIN sans AUCUN allie
    adjacent.

    Le temoin est a portee 3 ET a la MEME elevation que le caster : son refus ne peut venir ni du
    volet PORTEE ni du volet OBSCURCISSEMENT -- c'est la regle dynamique, et elle seule. AVANT
    #552 le port y rendait `0` (permissif) : cette garde est le cliquet de cette reparation.

    ANTI-DEGENERESCENCE : un accord ou TOUT vaut 0 ne prouverait rien -> on exige que le gate
    REFUSE soi, l'allie et le temoin, et ACCEPTE la cible."""
    dyn, ennemi = _target_matches_dynamic_rule(), _target_is_enemy()
    gp, gn = mc["gate_port"], mc["gate_natif"]
    assert gp == gn, "gate port %s != natif %s" % (
        {k: hex(v) for k, v in gp.items()}, {k: hex(v) for k, v in gn.items()})
    assert gp["cible"] == 0, "le gate REFUSE la cible que le natif accepte : %s" % hex(gp["cible"])
    assert gp["soi"] == ennemi and gp["allie"] == ennemi, \
        "REGIME DEGENERE : `TargetIsEnemy` ne refuse ni soi ni un allie -> %s" % {
            k: hex(v) for k, v in gp.items()}
    assert gp["ennemi_isole"] == dyn, \
        "la REGLE DYNAMIQUE ne refuse pas l'ennemi sans allie adjacent : %s (attendu %s)" % (
            hex(gp["ennemi_isole"]), hex(dyn))
    assert mc["regle_port"]["cible"] == 0 and mc["regle_port"]["ennemi_isole"] == dyn, \
        "la regle dynamique SEULE ne discrimine pas : %s" % mc["regle_port"]


def test_mind_control_decision_picks_the_highest_health_enemy(mc_dec):
    """FACE DECISION -- l'accord COMBAT n'en dit RIEN.

    `IdunBattle.AI.Playbook.Loki.MindControlPlaybook$$EvaluateNonComparable` =
    `Fix64(GetStat(cible, 5 = HEALTH))` : l'utilite EST les PV COURANTS de l'ENNEMI vise. Le
    montage pose DEUX ennemis legaux aux PV tres differents, l'ennemi FAIBLE etant le PREMIER
    enumere -- donc << premier enumere >> et << plus faible >> designent la MEME mauvaise unite,
    et l'accord ne peut pas etre accidentel.

    ⚠ La cible du COMBAT et celle de la DECISION sont deux unites DIFFERENTES (la decision classe
    les ENNEMIS, l'arbre classe mes ALLIES) : ce test est le seul qui garde la seconde."""
    assert mc_dec["hp"]["high"] > mc_dec["hp"]["low"], \
        "REGIME DEGENERE : les deux ennemis ont les memes PV (%s)" % mc_dec["hp"]
    assert mc_dec["from_here"] and mc_dec["from_here"][0] == mc_dec["low"], \
        "REGIME NON DISCRIMINANT : l'ennemi FAIBLE n'est pas le PREMIER enumere (%s) -- un port " \
        "qui prendrait le premier passerait" % mc_dec["from_here"]
    assert mc_dec["natif"]["ability"] == MIND_CONTROL, \
        "l'IA NATIVE ne propose pas 1164 (%s) -- l'oracle de decision est MUET, pas un vert" % (
            mc_dec["natif"],)
    assert mc_dec["natif"]["target"] == mc_dec["high"], \
        "l'IA NATIVE vise u%s, attendu l'ennemi a la plus haute Health u%s" % (
            mc_dec["natif"]["target"], mc_dec["high"])
    assert mc_dec["port"]["ability"] == MIND_CONTROL \
        and mc_dec["port"]["target"] == mc_dec["natif"]["target"], \
        "le PORT decide %s, le natif %s" % (mc_dec["port"], mc_dec["natif"])
    util = mc_dec["playbook_utilites"]
    assert util.get(mc_dec["high"]) == float(mc_dec["hp"]["high"]) \
        and util.get(mc_dec["low"]) == float(mc_dec["hp"]["low"]), \
        "l'utilite du playbook n'est PAS les PV courants de la cible : %s vs %s" % (
            util, mc_dec["hp"])


def test_mind_control_mask_has_exactly_one_source():
    """CONTRAT DE DISJONCTION : le masque de 1164 a MIGRE sur la classe, il ne doit plus vivre dans
    `TARGETING_OPTIONS_UNPORTED`. Deux sources divergeraient EN SILENCE."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    assert MIND_CONTROL in ABILITY_CLASSES, "1164 absente du registre COMBAT"
    assert getattr(ABILITY_CLASSES[MIND_CONTROL], "TARGETING_OPTIONS", None) is not None, \
        "1164 est au registre SANS son masque -- gate desarme, degradation permissive"
    assert MIND_CONTROL not in TARGETING_OPTIONS_UNPORTED, \
        "1164 est portee ET encore dans TARGETING_OPTIONS_UNPORTED (contrat de disjonction rompu)"
    assert MIND_CONTROL not in DYNAMIC_TARGET_RULE_UNPORTED, \
        "1164 est portee ET encore dans DYNAMIC_TARGET_RULE_UNPORTED (meme contrat)"
    assert "get_dynamic_invalid_target_reason" in ABILITY_CLASSES[MIND_CONTROL].__dict__, \
        "1164 pose `TargetMatchesDynamicRule` sans surcharger la regle -> defaut 0 = PERMISSIF"


def test_mind_control_attack_type_literal_is_transcribed():
    """`AActiveAbility..ctor(this, &opts, 0)` -> `AbilityAttackType.DirectTargetAttack`. LITTERAL
    transcrit, pas deduit : l'arbre de 1164 ne frappe PAS et le ctor dit quand meme `0` (meme
    contre-exemple que StormOfWrath 1019 et BloodyFury 1129). Une ability au registre SANS son
    litteral se degrade en silence (cf. `probe_120` etape 0)."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    assert ABILITY_ATTACK_TYPE.get(MIND_CONTROL) == AbilityAttackType.DirectTargetAttack, \
        "litteral de ctor absent ou faux : %s" % ABILITY_ATTACK_TYPE.get(MIND_CONTROL)


def test_mind_control_is_registered_as_noncomparable():
    """`MindControlPlaybook` derive de `NonComparablePlaybook` (chaine de parents LUE dans
    `data/symbols/<build>/frida/classes.tsv` -- le ctor gshared est mislabele
    `ComparablePlaybook<...>` par ghidra). Sans cette entree, la prediction fabriquerait un evenement
    de degat pour une ability qui n'en emet AUCUN."""
    from engine.entities.abilities.active_ability import makes_damage_predictions
    from engine.playbook.noncomparable import PLAYBOOKS
    assert makes_damage_predictions("MindControl") is False, \
        "1164 est traitee comme COMPARABLE -- elle n'a pas de `Make*Predictions`"
    assert MIND_CONTROL in PLAYBOOKS, "1164 absente du registre DECISION"
    assert PLAYBOOKS[MIND_CONTROL].MIN_UTILITY == 1.0, \
        "MIN_UTILITY %s -- le cctor natif pose `Fix64(1)`" % PLAYBOOKS[MIND_CONTROL].MIN_UTILITY
