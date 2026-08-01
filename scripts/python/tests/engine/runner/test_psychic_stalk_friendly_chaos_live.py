"""case-366-r1 -- GARDES de `1435 PsychicStalk_FriendlyChaosExtraDamage` (`thousAhriman`).

i2 : << Attacks that deal Flame Damage and Psychic Damage to enemies that are on hexes with Fire
deal +33% Damage. **Affected attacks from friendly Chaos units deal an additional +364 Damage.**
The hex of each enemy that is hit by Ahriman's normal ranged attack catches Fire. >>
(les trois phrases = TROIS effets distincts ; seule la DEUXIEME est `1435`.)

ARTEFACTS NATIFS (build rnca9r7q6c) :
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PsychicStalk_ExtraAttackDamageAbility$$CreateBehaviour`
      `AddEffect(0x4bf = 1215, ...) + AddEffect(0x4c0 = 1216, ...)
       + AddEffect(0x59b = 1435, <AbilityStateReference>, targets = Owner@0x30)`
      -> les TROIS effets vivent sur AHRIMAN, jamais sur l'attaquant beneficiaire.
  - `IdunBattle.Entities.Effects.Loki.PsychicStalk_FriendlyChaosExtraDamageEffect$$CreateEffectDamageBonusForAttack`
      `EffectBonus.ForAddition(
             AreFriends(Owner@0x30, Caster@0x48, comparisonType = 0, anyEntity = false)
           & HasTrait(Caster@0x48, 0x7ea = 2026 = Chaos)
           & GetTargetIsOnFireTileCondition() & GetAttackHasValidDamageProfileCondition(),
             ConfigVar(8 = extraDmg, GetAbilityState(effet), config@+0x60) )`
      La FABRIQUE est `ForAddition` -> ADDITIF **ATTAQUANT** (pre-percage, par coup). Ce n'est donc
      PAS le slot `pct_list` DEFENSEUR de son voisin `1215` (`ForPercentIncrease`) : deux entrees
      DIFFERENTES de `IdunBattle.Core.Services.DamageModifiers$$Add`, qui se COMPOSENT.
  - `IdunBattle.Entities.Effects.Loki.APsychicStalkEffect$$GetTargetIsOnFireTileCondition` /
    `$$GetAttackHasValidDamageProfileCondition` -- les DEUX conditions PARTAGEES avec `1215`.
  - CANAL consommateur : `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersFor
    Prediction` invoque le slot 0x16 sur la liste GLOBALE des entites porteuses d'effets actifs
    (double boucle `GetEnumerator`/`MoveNext`), SANS exclure le porteur --
    `IdunBattle.Entities.UnitExtensions$$IsFriend` compare deux `GetCurrentPlayer(...).index` et
    n'ecarte PAS l'egalite, donc `IsFriend(x, x)` est VRAI. Cote port cette enumeration se scinde
    en DEUX pattes DISJOINTES, exercees SEPAREMENT ici :
      * `create_effect_damage_bonus_for_attack`     (bras `--attacker ahriman`) ;
      * `create_aura_attack_damage_bonus_for_ally`  (bras `--attacker chaos-ally`).

CE QUE CES GARDES TIENNENT, et qui n'est tenu nulle part ailleurs :
  * L'ECART CHIFFRE que la PR de `1215` avait mesure SANS le fermer : sur MC1_67/31337, bras
    << Ahriman attaque >>, live [4253] contre port [3589] -- 664 = round(extraDmg[L50] x 1.8 x 1.33)
    = l'additif ATTAQUANT de `1435` (499 pre-percage) scale par le %-list DEFENSEUR de `1215`.
    Ces tests exigent desormais l'EGALITE, et la contre-epreuve `sans 1435` doit rendre [3589].
  * LES DEUX PATTES. Un port qui n'aurait que la patte SELF passerait le bras `ahriman` et
    ECHOUERAIT le bras `chaos-ally` -- et inversement.
  * L'ANTI-TEMOIN de gate : `astraPrimarisPsy` (Imperial, meme arme PSYCHIC r2, meme allie
    d'Ahriman) doit rendre `1435` MUET (`HasTrait(Caster, 0x7ea)`), donc `additive == 0` et
    `sans 1435 == avec 1435` au dernier bit.
  * L'ETAGE. `additive` (et pas `pct_list`) est ce qui distingue `ForAddition` de la fabrique du
    voisin. Un scalaire final ne dirait que << la somme colle >>.
  * Le NIVEAU. `ConfigVar(8)` s'indexe sur `GetAbilityState(effet)` ; l'`AbilityOrEffect` bake par
    la fabrique d'`EffectsDatabase` n'est PAS attribuable statiquement (le `.ctor` de la classe
    n'existe pas dans les tables -- corps mutualise avec `APsychicStalkEffect$$.ctor`, qui prend
    son `AbilityOrEffect` en PARAMETRE, cf. `reference_ctor_name_is_not_class_identity`). C'est le
    bras `--passive-level 1` qui TRANCHE : il dissocie le PASSIF (extraDmg = 9) de l'ACTIF (499),
    que `buildNormalizedBC` egalise a 50.
  * La RARETE. `extraDmg` EST dans `variablesAffectedByRarityBonus` (contrairement a l'`extraDmgPct`
    de `1215`) : un port qui l'oublierait rendrait 277 au lieu de 499 -- faux d'un FACTEUR.

Montage complet : `scripts/python/probe_366_r1_psychic_stalk_chaos.py`. ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_366_r1_psychic_stalk_chaos as PSC

# Deux couples (board, seed) -- discipline de generalisation (runner.md S3) : un resultat obtenu
# sur UN seul board peut etre un artefact de sa geometrie (distances, spawns, terrain).
COUPLES = (("MC1_67", "31337"), ("C4_09", "4242"))


@pytest.fixture(scope="module")
def psc_case(live_session, rpc):
    """Fabrique : `psc_case(board, seed, attacker, passive_level)` -> le dict de mesure du probe.

    [!] Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un
    regime non atteint est un VERT qui ment -- aucune mesure n'a eu lieu."""
    cache: dict = {}

    def _case(board: str = "MC1_67", seed: str = "31337", attacker: str = "ahriman",
              passive_level: "int | None" = None) -> dict:
        k = (board, seed, attacker, passive_level)
        if k not in cache:
            r = PSC.run(rpc, seed=seed, board_id=board, attacker=attacker,
                        passive_level=passive_level)
            if r.get("error"):
                pytest.fail("montage PsychicStalk/1435 NON INSTALLE (%s/%s/%s/lvl=%s): %s"
                            % (board, seed, attacker, passive_level, r["error"]))
            cache[k] = r
        return cache[k]
    return _case


def _assert_kit_posed(r):
    """E1 -- les TROIS effets du kit sont sur Ahriman, cote NATIF. Sans cette garde, un bras
    << port == live >> pourrait venir d'un kit absent, pas d'un gate correct."""
    assert r["e1_chaos_inactive_channel"] is True, (
        "natif : `1435` ABSENT des effets d'Ahriman au deploiement -- le passif n'est pas monte, "
        "la mesure ne porte sur rien (effets vus : %s)" % (r["e1_effects_on_carrier"],))
    assert r["e1_pct_inactive_channel"] is True, (
        "natif : `1215` absent -- le voisin qui compose avec `1435` n'est plus la (%s)"
        % (r["e1_effects_on_carrier"],))
    assert r["e1_visual_inactive_channel"] is True, (
        "natif : `1216` absent (%s)" % (r["e1_effects_on_carrier"],))


def _assert_port_view(r, expected_amount):
    """Ce que le PORT materialise, AVANT tout calcul de degat -- etage separe : un port qui n'a PAS
    l'effet et un port dont le gate ferme rendraient le meme degat. Les DEUX pattes y sont
    exercees sur le MEME ctx (elles partagent le corps natif : un seul `CreateEffectDamage
    BonusForAttack`)."""
    pv = r["b_port_effect_view"]
    assert pv.get("present") is True, (
        "le port ne materialise PAS 1435 sur la capture -- l'inscription `EFFECT_CLASSES` "
        "['PsychicStalk_FriendlyChaosExtraDamage'] manque (effets vus : %s)"
        % (pv.get("effects_on_carrier"),))
    assert pv.get("cls") == "PsychicStalkFriendlyChaosExtraDamageEffect", (
        "1435 est route sur %s (attendu PsychicStalkFriendlyChaosExtraDamageEffect)"
        % pv.get("cls"))
    # --- MAGNITUDE : `ConfigVar(8 = extraDmg)` x multiplier (var DANS variablesAffectedByRarityBonus)
    assert pv.get("self_nominal") == ["Addition", expected_amount], (
        "port : patte SELF = %s, attendu ['Addition', %s] = extraDmg[L%s] x mult %s%%. "
        "`ForAddition` (additif ATTAQUANT), PAS `ForPercentIncrease` (le slot de 1215). Un montant "
        "de %s trahirait un multiplier de rarete OUBLIE (extraDmg EST dans "
        "variablesAffectedByRarityBonus)."
        % (pv.get("self_nominal"), expected_amount, r["passive_level"], r["multiplier"],
           round(expected_amount / ((r["multiplier"] or 100) / 100.0))))
    assert pv.get("aura_nominal") == ["Addition", expected_amount], (
        "port : patte AURA = %s, attendu ['Addition', %s] -- les deux pattes partagent le MEME "
        "corps natif, elles doivent rendre le MEME montant"
        % (pv.get("aura_nominal"), expected_amount))
    # --- GATE `GetTargetIsOnFireTileCondition` (partage avec 1215)
    assert pv.get("self_no_fire") is None, (
        "port : le gate `GetTargetIsOnFireTileCondition` ne ferme pas sur une tuile SANS feu "
        "(bonus rendu : %s)" % (pv.get("self_no_fire"),))
    assert pv.get("self_no_tile_channel") is None, (
        "port : canal d'effets de tuile ABSENT -> le port contribue quand meme (%s). La "
        "degradation doit etre << present != applique >>." % (pv.get("self_no_tile_channel"),))
    # --- GATE `HasTrait(Caster@0x48, 0x7ea = Chaos)` -- LE gate qui separe 1435 de 1215
    assert pv.get("self_imperial") is None, (
        "port : le gate `HasTrait(Caster@0x48, 0x7ea = Chaos)` laisse passer un attaquant de "
        "grande-alliance Imperial (%s) -- c'est le SEUL gate qui separe 1435 de son voisin 1215"
        % (pv.get("self_imperial"),))
    assert pv.get("self_ga_unknown") is None, (
        "port : grande-alliance de l'attaquant NON THREADEE -> le port contribue quand meme (%s)"
        % (pv.get("self_ga_unknown"),))
    # --- GATE `GetAttackHasValidDamageProfileCondition` (partage avec 1215)
    assert pv.get("self_profile_physical") is None, (
        "port : le gate `DamageProfileIs([Flame, Psychic])` laisse passer un profil Physical (%s)"
        % (pv.get("self_profile_physical"),))
    assert pv.get("self_profile_none") is None, (
        "port : profil NON THREADE -> le port contribue quand meme (%s)"
        % (pv.get("self_profile_none"),))
    assert pv.get("self_profile_flame") == ["Addition", expected_amount], (
        "port : le profil FLAME (2e valeur de la liste, `GetAffectedDamageProfile() ?? 3`) ne "
        "passe PAS le gate (%s) -- seul Psychic serait accepte" % (pv.get("self_profile_flame"),))
    # --- GATE `AreFriends(Owner@0x30, Caster@0x48)` -- patte AURA seulement (la patte SELF a
    #     `Owner == Caster`, donc `IsFriend(x, x)` = VRAI, lu au decompile).
    assert pv.get("aura_enemy_attacker") is None, (
        "port : le gate `AreFriends(Owner@0x30, Caster@0x48)` laisse passer un attaquant d'une "
        "AUTRE equipe que le porteur (%s)" % (pv.get("aura_enemy_attacker"),))
    assert pv.get("aura_team_unknown") is None, (
        "port : equipe de l'attaquant NON THREADEE -> l'aura contribue quand meme (%s)"
        % (pv.get("aura_team_unknown"),))


def _assert_stage_is_additive(r, expected_amount):
    """DECOMPOSITION PAR ETAGE : le canal ecrit-il dans LE bon slot ? `ForAddition` -> `additive`
    des modifiers ATTAQUANT. `pct_list` ATTAQUANT non vide trahirait un `ForPercentIncrease`
    (la fabrique de `1215`, qui vit lui sur le canal DEFENSEUR)."""
    st, sw = r["b_stage_with"], r["b_stage_without"]
    assert st["additive"] == expected_amount, (
        "port : l'additif ATTAQUANT vaut %s, attendu %s -- le canal n'ecrit pas le bon montant "
        "dans le bon slot" % (st["additive"], expected_amount))
    assert sw["additive"] == 0, (
        "port : l'additif ATTAQUANT n'est PAS nul sans `1435` (%s) -- une AUTRE source contribue, "
        "l'attribution du bras est cassee" % (sw["additive"],))
    assert st["pct_list"] == [] and st["flat_reductions"] == [], (
        "port : le canal a ecrit dans `pct_list`/`flat_reductions` ATTAQUANT (%s / %s) -- ce sont "
        "les slots de `ForPercentIncrease`/`ForSubtraction`, pas celui de `ForAddition`"
        % (st["pct_list"], st["flat_reductions"]))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_psychic_stalk_chaos_self_leg_live(psc_case, board, seed):
    """PATTE SELF -- Ahriman (Chaos) attaque lui-meme. C'est le bras que la PR de `1215` avait
    CHIFFRE sans le fermer : MC1_67/31337 live [4253] / port [3589], ecart 664.

    Le natif applique le slot 0x16 a TOUS les effets actifs de l'etat, porteur INCLUS
    (`UnitExtensions$$IsFriend` n'ecarte pas l'egalite) -> l'effet pose sur Ahriman bonifie SA
    PROPRE attaque, et le port doit le rendre par `create_effect_damage_bonus_for_attack`."""
    r = psc_case(board, seed, "ahriman")
    amt = r["extra_dmg_passive"]
    print("\n[366-r1/1435 self %s/%s] %s" % (board, seed, {
        "extraDmg": amt, "live": r["b_live_hits"], "port": r["b_port_hits"],
        "sans_1435": r["b_port_hits_without_1435"],
        "sans_1215": r["b_port_hits_without_1215"],
        "sans_feu": r["b_port_hits_without_fire"], "etage": r["b_stage_with"]}))

    assert amt, ("extraDmg irresoluble au niveau PASSIF %s -- la config d'ability a bouge ?"
                 % r["passive_level"])
    _assert_kit_posed(r)
    _assert_port_view(r, amt)
    _assert_stage_is_additive(r, amt)

    assert r["b_target_on_fire"] is True, (
        "natif : la cible n'est PAS sur un hex en feu au moment du coup -- le regime n'est pas "
        "installe (hexes en feu : %s)" % (r["b_fire_tiles"],))
    assert not r["b_dirty"], "coup non propre (crit/block/evade) -- le bonus n'est pas isole"
    assert r["b_port_hits"] == r["b_live_hits"], (
        "port %s != natif %s -- l'ecart de la PR de 1215 (664 = extraDmg x %%-list) n'est PAS ferme"
        % (r["b_port_hits"], r["b_live_hits"]))
    # CONTRE-EPREUVE de discriminance : sans `1435`, MEME capture, MEME flux MT.
    assert r["b_port_hits_without_1435"] != r["b_port_hits"], (
        "regime NON DISCRIMINANT : retirer 1435 ne change RIEN au degat (%s) -- la mesure ne "
        "prouve rien" % (r["b_port_hits"],))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_psychic_stalk_chaos_aura_leg_live(psc_case, board, seed):
    """PATTE AURA -- `thousSorcerer` (Chaos / ThousandSons, arme PSYCHIC r2) attaque : il beneficie
    de l'effet pose sur AHRIMAN via `create_aura_attack_damage_bonus_for_ally`.

    Un port qui n'aurait que la patte SELF passe le test precedent et ECHOUE ici."""
    r = psc_case(board, seed, "chaos-ally")
    amt = r["extra_dmg_passive"]
    print("\n[366-r1/1435 aura %s/%s] %s" % (board, seed, {
        "attaquant": r["attacker_visual"], "extraDmg": amt,
        "live": r["b_live_hits"], "port": r["b_port_hits"],
        "sans_1435": r["b_port_hits_without_1435"], "etage": r["b_stage_with"]}))

    assert r["attacker_visual"] != r["carrier_id"], "sanity : l'attaquant n'est pas le porteur"
    assert r["att_id"] != r["carrier_id"], (
        "le bras AURA doit avoir un attaquant DIFFERENT du porteur -- sinon il re-teste la patte "
        "SELF (att=%s carrier=%s)" % (r["att_id"], r["carrier_id"]))
    _assert_kit_posed(r)
    _assert_port_view(r, amt)
    _assert_stage_is_additive(r, amt)

    assert r["b_target_on_fire"] is True, "regime non installe (cible hors hex en feu)"
    assert not r["b_dirty"], "coup non propre (crit/block/evade)"
    assert r["b_port_hits"] == r["b_live_hits"], (
        "port %s != natif %s -- la patte AURA (`create_aura_attack_damage_bonus_for_ally`) ne "
        "reproduit pas ce que le natif accorde a un ALLIE Chaos du porteur"
        % (r["b_port_hits"], r["b_live_hits"]))
    assert r["b_port_hits_without_1435"] != r["b_port_hits"], (
        "regime NON DISCRIMINANT : retirer 1435 ne change RIEN (%s)" % (r["b_port_hits"],))


def test_psychic_stalk_chaos_non_chaos_attacker_is_mute(psc_case):
    """ANTI-TEMOIN du gate `HasTrait(Caster@0x48, 0x7ea = Chaos)`. `astraPrimarisPsy` est Imperial,
    ALLIE d'Ahriman, avec la MEME arme PSYCHIC r2 et la MEME cible sur le MEME hex en feu : la
    SEULE variable qui bouge est la grande-alliance de l'attaquant.

    `1435` doit etre MUET -- `additive == 0`, et surtout `sans 1435 == avec 1435` AU DERNIER BIT
    (une egalite de degat seule ne prouverait rien : elle peut venir d'un port qui n'a pas l'effet).
    MESURE (MC1_67/31337) : live [3993] == port [3993] == port sans 1435."""
    r = psc_case("MC1_67", "31337", "imperial")
    print("\n[366-r1/1435 anti-temoin Imperial] %s" % ({
        "attaquant": r["attacker_visual"], "live": r["b_live_hits"], "port": r["b_port_hits"],
        "sans_1435": r["b_port_hits_without_1435"],
        "sans_1215": r["b_port_hits_without_1215"], "etage": r["b_stage_with"]},))

    _assert_kit_posed(r)
    assert r["b_target_on_fire"] is True, "regime non installe (cible hors hex en feu)"
    assert not r["b_dirty"], "coup non propre (crit/block/evade)"
    assert r["b_port_effect_view"].get("present") is True, (
        "le port ne materialise pas 1435 -- ce bras ne mesure alors pas un GATE ferme mais une "
        "absence d'effet")
    assert r["b_stage_with"]["additive"] == 0, (
        "port : l'additif ATTAQUANT vaut %s pour un attaquant NON-Chaos -- le gate "
        "`HasTrait(Caster@0x48, 0x7ea)` ne ferme pas" % (r["b_stage_with"]["additive"],))
    assert r["b_port_hits_without_1435"] == r["b_port_hits"], (
        "port : retirer 1435 CHANGE le degat (%s -> %s) alors que l'attaquant n'est pas Chaos -- "
        "l'effet contribue par un chemin qui ignore son gate"
        % (r["b_port_hits"], r["b_port_hits_without_1435"]))
    assert r["b_port_hits"] == r["b_live_hits"], (
        "port %s != natif %s sur le bras ou seul `1215` contribue -- la regression touche le "
        "voisin, pas 1435" % (r["b_port_hits"], r["b_live_hits"]))
    # ... et `1215`, lui, contribue bien : sans lui le degat CHANGE. Sans cette ligne, un port
    # ou les DEUX effets seraient morts passerait ce test.
    assert r["b_port_hits_without_1215"] != r["b_port_hits"], (
        "bras NON DISCRIMINANT : ni 1435 ni 1215 ne changent quoi que ce soit (%s)"
        % (r["b_port_hits"],))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_psychic_stalk_chaos_fire_tile_gate_live(psc_case, board, seed):
    """Le gate PARTAGE `GetTargetIsOnFireTileCondition`, exerce des DEUX bouts sur le bras SELF :

      * LIVE -- au tour 1 la cible n'est sur AUCUN hex en feu ; l'effet est pourtant PRESENT sur
        Ahriman. Le natif ne bonifie pas, le port non plus (`live == port`).
      * OFFLINE -- CONTREFACTUEL de tuile sur la capture du tour 2 : on eteint le feu sous la
        cible, et le port doit alors perdre les DEUX contributions (1435 ET 1215, qui partagent
        ce gate) -- donc rendre STRICTEMENT moins que le retrait du seul 1435."""
    r = psc_case(board, seed, "ahriman")
    print("\n[366-r1/1435 gate-feu %s/%s] %s" % (board, seed, {
        "a_feu_sous_cible": r["a_target_on_fire"], "a_live": r["a_live_hits"],
        "a_port": r["a_port_hits"], "e3_hexes_en_feu": r["e3_fire_tiles"],
        "b_port": r["b_port_hits"], "b_sans_feu": r["b_port_hits_without_fire"],
        "b_sans_1435": r["b_port_hits_without_1435"]}))

    _assert_kit_posed(r)
    assert r["a_target_on_fire"] is False, (
        "le bras SANS FEU part deja avec un hex en feu sous la cible (%s) -- il ne mesure pas le "
        "gate ferme" % (r["a_fire_tiles"],))
    assert not r["a_dirty"], "coup A non propre (crit/block/evade)"
    assert r["a_port_hits"] == r["a_live_hits"], (
        "gate FERME : port %s != natif %s -- l'un des deux applique un bonus que l'autre ignore"
        % (r["a_port_hits"], r["a_live_hits"]))
    # E3 : la pose du feu par le natif (`PsychicStalk_ApplyFireTileAbility`) est ce qui rend le
    # bras AVEC FEU possible ; sans elle le test ci-dessus serait le seul regime jouable.
    assert r["e3_target_on_fire"] is True, (
        "natif : l'attaque normale RANGED d'Ahriman n'a PAS allume l'hex de la cible "
        "(hexes en feu : %s)" % (r["e3_fire_tiles"],))
    # Le contrefactuel de TUILE coupe les DEUX effets, le retrait de 1435 n'en coupe qu'UN.
    assert r["b_port_hits_without_fire"] != r["b_port_hits_without_1435"], (
        "port : eteindre le feu (%s) donne le MEME degat que retirer le seul 1435 (%s) -- le gate "
        "de tuile ne coupe donc pas AUSSI la contribution de 1215, l'attribution est fausse"
        % (r["b_port_hits_without_fire"], r["b_port_hits_without_1435"]))
    assert r["b_port_hits_without_fire"] != r["b_port_hits"], (
        "le contrefactuel de tuile ne CHANGE rien (%s) : la mesure ne discrimine pas"
        % (r["b_port_hits"],))


def test_psychic_stalk_chaos_magnitude_indexed_by_passive_level(psc_case):
    """DISCRIMINANT de NIVEAU. `--unit-stat "thousAhriman:PassiveAbilityLevel=1"` dissocie le PASSIF
    de l'ACTIF (que `buildNormalizedBC` egalise a 50) : c'est le SEUL regime qui distingue les deux
    lectures possibles de `GetAbilityState(effet)`, que la RE ne peut PAS trancher statiquement (le
    `.ctor` de `PsychicStalk_FriendlyChaosExtraDamageEffect` n'existe pas dans les tables -- corps
    mutualise avec `APsychicStalkEffect$$.ctor`, qui prend son `AbilityOrEffect` en PARAMETRE, et
    les deux lambdas nommees qui appellent ce corps bakent `1157`/`1219`, ni l'une ni l'autre
    n'etant `TriggeredAbilityType.PsychicStalk = 1179`).

    MESURE (MC1_67/31337, passif 1 / actif 50) : natif [3522] = extraDmg[L1] x 1.8 = 9 ; le meme
    rejeu force au niveau ACTIF (499) donnerait [4134]. Le regime discrimine donc bien, et c'est
    le PASSIF qui est lu."""
    r = psc_case("MC1_67", "31337", "ahriman", 1)
    amt_p, amt_a = r["extra_dmg_passive"], r["extra_dmg_active"]
    print("\n[366-r1/1435 niveau-passif] %s" % ({
        "passif": r["passive_level"], "actif": r["active_level"],
        "extraDmg_passif": amt_p, "extraDmg_actif": amt_a, "live": r["b_live_hits"],
        "port": r["b_port_hits"], "port_si_actif": r["b_port_hits_active_level"],
        "etage": r["b_stage_with"]},))

    assert r["passive_level"] == 1, (
        "le patch `PassiveAbilityLevel=1` n'a pas pris (combatSnapshot expose L%s) -- le regime "
        "n'est pas installe, la mesure ne discrimine rien" % (r["passive_level"],))
    assert r["passive_level"] != r["active_level"], (
        "passif == actif == %s : regime NON DISCRIMINANT" % (r["passive_level"],))
    assert amt_p != amt_a, (
        "extraDmg[passif L%s] == extraDmg[actif L%s] == %s : les deux niveaux tombent sur la MEME "
        "valeur de config -- choisir un autre niveau"
        % (r["passive_level"], r["active_level"], amt_p))
    _assert_kit_posed(r)
    _assert_port_view(r, amt_p)
    _assert_stage_is_additive(r, amt_p)
    assert not r["b_dirty"], "coup non propre (crit/block/evade)"
    assert r["b_port_hits"] == r["b_live_hits"], (
        "port %s != natif %s -- si l'ecart vaut celui du niveau ACTIF (%s), c'est l'AbilityState de "
        "l'ACTIVE que le natif resout, pas celle du PASSIF"
        % (r["b_port_hits"], r["b_live_hits"], r["b_port_hits_active_level"]))
    # CONTREFACTUEL DE NIVEAU : sans lui, << live == port >> ne prouverait rien si les deux niveaux
    # donnaient la meme valeur tiree (le regime NOMINAL est DEGENERE : passif == actif == 50).
    assert r["b_port_hits_active_level"] != r["b_port_hits"], (
        "le contrefactuel de niveau ACTIF rend le MEME degat (%s) : le regime ne discrimine pas "
        "les deux lectures" % (r["b_port_hits"],))
