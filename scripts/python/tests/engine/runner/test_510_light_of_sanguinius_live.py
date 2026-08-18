"""GARDE de `1177 LightOfSanguinius` (#510) -- les DEUX faces, et l'effet 1376 qu'elle pose.

Avant #510 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la face
DECISION la choisissait (playbook porte, `playbook/loki_custom.py`) et l'execution l'ignorait --
0 degat, 0 vol, 0 debuff, AUCUNE erreur. Ce fichier garde ce que le port doit desormais produire,
confronte au NATIF sur le MEME substrat.

SIX ETAGES, tous portes par `probe_510_light_of_sanguinius_live.py` (foyer unique -- ce fichier ne
duplique NI le montage NI les criteres, meme discipline que `test_504_kill_maim_burn_live.py`) :

  E1 CAST    la SEQUENCE des coups tagges `Active_Ability_Type == 1177`, port vs live, depuis la
             MEME capture et le MEME Mersenne Twister (`dumpRng`). Un critere sur le TOTAL serait
             reste vert sur une cible surtuee.
  E2 VOL     la tuile d'arrivee de `FlyUnit(Caster, First(SortTilesByUtility(...)))`.
  E3 AURA    l'ENSEMBLE des porteurs de l'effet 1376 apres le cast -- le seul etage qui exerce
             `Target + NonSteppableOrObjectUnits(Enemies(SurroundingUnits(Target, range_2)))`.
             Un ennemi HORS du ring est au montage : il doit rester NON affecte.
  E4 DEBUFF  oracle natif `aiPlaybookPredict(<attaque normale concrete>)` vs prediction PORTEE, sur
             chaque couple (ennemi, allie), PENDANT LE TOUR DE L'EQUIPE AFFECTEE. Le montage porte
             DEUX defenseurs de meme `Health` et de PV restants differents (100 % / 40 %), donc les
             DEUX magnitudes de `LightOfSanguinius_DamageReductionEffect$$CreateDamageModifier`
             (`-dmgReductionPct %` et son DOUBLE sous `healthPct`), plus un TEMOIN non affecte.
  E5 COMBAT  l'attaque REELLE d'une unite affectee, rejouee OFFLINE deux fois -- doublement ARME et
             DESARME. Une seule des deux peut etre bit-exacte : c'est ce qui tranche.
  E6 ANTI-CONFOND  la prediction native RE-MESUREE au MEME instant que l'attaque de combat.

⚠ CE QUE CE FICHIER GARDE AUSSI, PARCE QUE CA A COUTE UN PORT FAUX : `aiPlaybookPredict` interroge
sur une unite qui n'est PAS de l'equipe ACTIVE rend une prediction a CONTEXTE DEGRADE -- le
doublement y est ABSENT dans TOUS les regimes. Un premier port avait donc conclu a un « fork
prediction/combat » et gate le doublement sur `is_prediction` ; l'anti-confond (meme couple, meme
effet, meme instant, apres `endturn`) l'a REFUTE. Le probe imprime la grille HORS-TOUR a cote de la
grille EN-TOUR pour que le piege reste visible.

Le montage EXIGE ses regimes ; s'il ne les obtient pas il ECHOUE, il ne skippe pas (#268) -- sauf
indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        # Elles portent des fixtures `autouse` dont le verdict de CHAQUE test depend, et aucun
        # test ne les IMPORTE (semantique pytest) -- donc aucun graphe d'imports ne les verrait.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les criteres, et les deux probes
        # dont il tire ses helpers de runner :
        "scripts/python/probe_510_light_of_sanguinius_live.py",
        "scripts/python/probe_112_darkangels.py",
        "scripts/python/probe_226_hammer_foehammer.py",
        "scripts/python/probe_27_custom_utility_inventory.py",
        "scripts/python/rl_duel.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu passe par `Runner.apply(ActiveAbilityMessage)`
        # ET par `Runner.apply(AttackUnitMessage)`, plus la face PREDICTION complete
        # (`playbook/prediction/**`) -- donc la fermeture d'imports MESUREE traverse le pipeline de
        # degat, le PRNG, le pathfinding, la cascade de ciblage, le tri par utilite et la couche
        # d'effets, tous capables de deplacer une valeur bit-exacte. Enumerer les seuls fichiers de
        # #510 serait DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX VERT.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1177 (arbre DSL `runner/abilities/bloodangels.py` : `AddEffect` "
              "Infiltrate, `FlyUnit` sur le collapse `charge_dest_tile` partage avec 1153, "
              "`AttackWithAttackDamage` famille ATTACK, `AddEffect` de l'aura sur "
              "`Target + NonSteppableOrObjectUnits(Enemies(SurroundingUnits))`), l'effet 1376 "
              "`LightOfSanguiniusDmgReductionEffect` (`entities/effects/loki/damage_reduction.py`) "
              "et son substrat `tgt_hp`/`tgt_hp_max` threade par les trois faces "
              "(`runner/damage_model.py`, `playbook/prediction/normal_attack.py`, "
              "`playbook/prediction/abilities.py`), plus le cablage (registre `ABILITY_CLASSES`, "
              "`ABILITY_ATTACK_TYPE`, masque migre depuis `targeting.py`) -- et tout le moteur que "
              "le rejeu hors-ligne traverse. `build: True` parce que les etages E1 et E5 "
              "confrontent le NATIF au coup pres.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_510_light_of_sanguinius_live as P                 # noqa: E402


@pytest.fixture(scope="module")
def mesure():
    """UN seul montage, UN seul cast natif, UN seul tour adverse : le runner est cher et les six
    etages se lisent sur la MEME bataille (c'est aussi ce qui rend l'anti-confond E6 valide -- il
    exige le MEME instant que E5)."""
    a = P._parser().parse_args([
        "--state-file", "t510_%d.json" % os.getpid(),          # isole par PID (probes en //)
    ])
    try:
        verdicts = P.mesure(a)
    except Exception as e:                                     # host injoignable != verdict du port
        pytest.skip("host/session indisponible (%s)" % (e,))
    if verdicts is None:
        pytest.skip("montage KO (build/session) -- pas un verdict sur le port")
    return verdicts


# ---------------------------------------------------------------- 0. le cablage, hors live

def test_le_cablage_du_registre_est_complet():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son masque ET son `AbilityAttackType`
    DANS LE MEME COMMIT, et SORT de `TARGETING_OPTIONS_UNPORTED` (contrat de DISJONCTION : une
    ability a UNE source de masque, jamais deux). Sans masque, `get_invalid_target_reason` rend 0
    et le moteur accepte des casts que `ActiveAbilityOperation$$IsInvalidTarget` REFUSE."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.runner.abilities.targeting import RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    los = int(ActiveAbilityType.LightOfSanguinius)             # 1177
    cls = ABILITY_CLASSES.get(los)
    assert cls is not None, "1177 absente d'ABILITY_CLASSES : c'est le NO-OP d'avant #510"
    assert los not in TARGETING_OPTIONS_UNPORTED, (
        "1177 est portee ET encore dans TARGETING_OPTIONS_UNPORTED (disjonction rompue)")
    assert los not in DYNAMIC_TARGET_RULE_UNPORTED, (
        "1177 est portee ET sa regle dynamique vit encore dans DYNAMIC_TARGET_RULE_UNPORTED : "
        "la classe la SURCHARGE desormais, les deux sources se contrediraient")
    opts = getattr(cls, "TARGETING_OPTIONS", None)
    assert opts is not None, "1177 au registre SANS masque = gate de ciblage DESARME"
    # `<TargetingOptions statics>+0x268` = `<preset +0x240>+0x28`, LU dans le `.cctor`. La somme est
    # EXHAUSTIVE : aucun bit residuel, et le bit 32 (`TargetIsNotAdjacent`) est au-dela de 32.
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.CasterHasNotMoved
                                  | TR.TargetHasFreeAdjacentTile | TR.TargetIsEnemy
                                  | TR.AllowObscuredTargetByElevation | TR.TargetIsNotAdjacent)
    assert int(opts.rules) == 0x102004032
    assert opts.self_cast is False
    assert opts.range == RANGE_WHOLE_BOARD          # `TargetingRange` statics+0x48 = useWholeBoard
    assert opts.force_melee_target == RANGED_BOOL_FALSE                    # `<preset>+0x260` = 1
    # 3e argument d'`AActiveAbility$$.ctor`, transcrit TEL QUEL (jamais deduit du profil de degat).
    assert ABILITY_ATTACK_TYPE.get(los) == AbilityAttackType.DirectTargetAttack

    # `1204 LeadingTheCharge` partage le MEME preset `<TargetingOptions statics>+0x240`, donc le
    # MEME masque -- ce qui les separe est leur `GetDynamicInvalidTargetReason`, pas leurs options.
    # Sa face COMBAT a ete portee par #508, une tranche PARALLELE : les DEUX jumeaux portent
    # desormais leur masque SUR LEUR CLASSE, avec la MEME valeur.
    # ⚠ Ce temoin etait ecrit « 1204 doit RESTER dans la table des non-portees » ; il est tombe au
    # rebase sur #508. Un temoin fige dans une table qui RETRECIT a chaque port est une peremption
    # programmee (meme gisement que le cobaye de `test_433_r4_r2_r1_r2_ability_range_offline`).
    lead = int(ActiveAbilityType.LeadingTheCharge)
    lead_cls = ABILITY_CLASSES.get(lead)
    assert lead_cls is not None and lead not in TARGETING_OPTIONS_UNPORTED
    assert int(lead_cls.TARGETING_OPTIONS.rules) == int(opts.rules)
    # ⚠ IL Y AVAIT ICI UN PLANCHER -- `assert len(TARGETING_OPTIONS_UNPORTED) > 10`, ecrit pour dire
    # « le retrait de 1177 est CIBLE, pas un effacement ». Il a rendu `master` ROUGE en tombant sur
    # le PROGRES : la table est VIDE depuis `c3eb44a2` (#996-r1-r3, 2026-08-14, `1015 PrecisionShot`
    # -- « actives=175 ported=174 no-op=0 »), les 15+ entrees en etant sorties une a une par
    # MIGRATION de leur masque sur leur classe, chaque sortie etant nommee dans `targeting.py`.
    # PREMISSE EXPIREE, donc, et le plancher RETIRE -- sans remplacant, parce que la mesure dit
    # qu'un remplacant serait DOMINE. Les SEPT mutations jouees a l'ablation, et l'assertion qui
    # tombe en TETE pour chacune :
    #     1177 sort du registre .................. l.135 `cls is not None`
    #     1177 revient dans la table ............. l.136 disjonction
    #     masque efface de la classe ............. l.142 `opts is not None`
    #     masque FAUX (0x4002) ................... l.145 la somme de bits
    #     `AbilityAttackType` absent ............. l.153
    #     le temoin 1204 sort du registre ........ l.164
    #     table RE-PEUPLEE a 12 entrees BIDON .... AUCUNE -- le plancher etait satisfiable par du BRUIT
    # Le plancher n'arrive en tete d'AUCUNE des six mutations reelles, et la septieme montre qu'il ne
    # distinguait pas une table peuplee legitimement d'une table peuplee n'importe comment.
    # NE PAS EN REPOSER UN. Ce que le plancher pretendait garder est tenu ailleurs, en INVARIANT :
    #   * `tests/engine/runner/test_targeting_options_sources.py` --
    #     `test_la_deuxieme_source_reste_CONSULTEE_meme_table_vide` injecte une entree BIDON par
    #     monkeypatch, donc le MECANISME de la 2e source est garde INDEPENDAMMENT du contenu de la
    #     table (5 passed) ; `test_les_deux_sources_de_masque_sont_disjointes` garde le contrat ;
    #   * `probe_181_targeting_gaps.py` -- « masques manquants == 0 » sur tout le registre
    #     (182/182 au 2026-08-18), l'invariant que CLAUDE.md oppose deja explicitement aux seuils.


def test_l_effet_1376_est_enregistre_et_porte_ses_deux_magnitudes():
    """`LightOfSanguinius` (1376) doit resoudre sur sa CLASSE (pas sur un `BaseEffect` nu, qui ne
    contribuerait RIEN), et rendre `-dmgReductionPct %` puis son DOUBLE selon les PV du DEFENSEUR.
    Les deux magnitudes sont DERIVEES du gameconfig, jamais ecrites en dur ici."""
    import gameconfig as GC
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import EFFECT_CLASSES, EffectFactory
    from engine.entities.effects.loki.damage_reduction import LightOfSanguiniusDmgReductionEffect

    nom = EffectType.LightOfSanguinius.name
    assert EFFECT_CLASSES.get(nom) is LightOfSanguiniusDmgReductionEffect

    cfg = GC.ability("LightOfSanguinius") or {}
    seuil = int((cfg.get("constants") or {})["healthPct"])              # ConfigConst(0x4f)
    niveau = 50
    pct = int((cfg.get("variables") or {})["dmgReductionPct"][niveau - 1])   # ConfigVar(0x46)
    assert pct > 0 and 0 < seuil < 100, "gameconfig : le montage du test est vide"

    eff = EffectFactory.create({"name": nom, "effectType": int(EffectType.LightOfSanguinius)},
                               active_ability_level=niveau)
    # defenseur AU-DESSUS du seuil -> `NOT(HealthPctIsBelowOrEqual)` VRAI -> `pct` simple
    haut = eff.create_effect_damage_bonus_for_attack(att_ctx={"tgt_hp": 100, "tgt_hp_max": 100})
    # defenseur AU seuil EXACT -> comparaison INCLUSIVE (`op_LessThanOrEqual`) -> DOUBLE
    bord = eff.create_effect_damage_bonus_for_attack(
        att_ctx={"tgt_hp": seuil, "tgt_hp_max": 100})
    # substrat ABSENT -> degradation RESTRICTIVE (pas de doublement invente)
    muet = eff.create_effect_damage_bonus_for_attack(att_ctx={})
    for b in (haut, bord, muet):
        assert b is not None and b.kind == "PercentDecrease" and b.owner_is_caster is True
    assert haut.value == pct
    assert bord.value == 2 * pct
    assert muet.value == pct
    # AUCUN gate `is_prediction` : le doublement est mesure sur les DEUX faces (cf. E4/E5/E6).
    pred = eff.create_effect_damage_bonus_for_attack(
        is_prediction=True, att_ctx={"tgt_hp": seuil, "tgt_hp_max": 100})
    assert pred.value == 2 * pct, (
        "un gate `is_prediction` a ete re-introduit -- il a ete REFUTE par l'anti-confond E6")


def test_le_substrat_pv_est_threade_par_les_trois_faces():
    """`tgt_hp`/`tgt_hp_max` = l'entree du gate `HealthPctIsBelowOrEqual(Target@+0x60, ...)`. Le
    natif n'a qu'UN `AbilityEntities` ; la scission combat/prediction est un artefact du PORT, donc
    les TROIS sites doivent poser les MEMES cles -- sinon le doublement existe d'un cote et pas de
    l'autre, exactement le fork qu'on a cru lire puis refute."""
    import re
    from pathlib import Path
    racine = Path(_PY) / "engine"
    sites = ["runner/damage_model.py",
             "../engine/playbook/prediction/normal_attack.py",
             "../engine/playbook/prediction/abilities.py"]
    for s in sites:
        txt = (racine / s).resolve().read_text(encoding="utf-8")
        assert re.search(r'"tgt_hp"', txt), "%s ne threade plus `tgt_hp`" % s
        assert re.search(r'"tgt_hp_max"', txt), "%s ne threade plus `tgt_hp_max`" % s


# ---------------------------------------------------------------- 1..6. les etages LIVE

def test_e1_le_cast_est_bit_exact(mesure):
    """La SEQUENCE des coups (nrOfHits x Melta), pas leur somme."""
    assert mesure.get("E1 cast bit-exact") is True


def test_e2_la_tuile_de_vol_est_celle_du_natif(mesure):
    """`FlyUnit(Caster, First(SortTilesByUtility(Filter(CanAddUnit(AdjacentTiles(Target)), ...))))`
    -- le collapse partage avec `HammerOfWrathAbility` (`charge_dest_tile`)."""
    assert mesure.get("E2 tuile de vol") is True


def test_e3_l_aura_frappe_la_cible_et_ses_voisins_ennemis_seulement(mesure):
    """`Target + NonSteppableOrObjectUnits(Enemies(SurroundingUnits(Target, range_2)))` : l'ennemi
    place HORS du ring doit rester NON affecte (c'est le temoin qui rend cet etage non degenere)."""
    assert mesure.get("E3 porteurs de l'aura") is True


def test_e4_la_prediction_portee_reproduit_l_oracle_natif(mesure):
    """Sur CHAQUE couple (ennemi, allie), pendant le tour de l'equipe affectee."""
    assert mesure.get("E4 port == oracle natif") is True


def test_e4_le_debuff_mord_et_le_temoin_reste_plat(mesure):
    """TEMOIN NON NUL : les affectes baissent, les non-affectes ne bougent pas. Sans ce couple de
    criteres, un accord en regime degenere (« tout a baisse » / « rien n'a bouge ») passerait."""
    assert mesure.get("E4 le debuff MORD (affectes)") is True
    assert mesure.get("E4 temoin PLAT (non affecte)") is True


def test_e5_le_combat_est_bit_exact_et_le_doublement_mord(mesure):
    """Le rejeu OFFLINE avec doublement ARME est bit-exact vs live, et le bras DESARME ne l'est
    PAS -- c'est ce second point qui interdit un vert par coincidence."""
    assert mesure.get("E5 harnais deterministe (defenseur 40pc PV)") is True
    assert mesure.get("E5 port == live (defenseur 40pc PV)") is True
    assert mesure.get("E5 combat DOUBLE (bras arme bit-exact)") is True


def test_e6_anti_confond_prediction_et_combat_au_meme_instant(mesure):
    """La prediction native RE-MESUREE a l'instant de l'attaque porte le MEME doublement : il n'y a
    PAS de fork prediction/combat. C'est la garde qui empeche de re-poser le gate `is_prediction`
    sur la foi d'une mesure HORS-TOUR."""
    assert mesure.get("E6 prediction ET combat doublent au MEME instant") is True
