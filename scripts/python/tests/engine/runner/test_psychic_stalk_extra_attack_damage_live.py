"""case-366-r1 -- GARDES de `1215 PsychicStalk_ExtraAttackDamage` (`thousAhriman` <<Ahriman>>).

i2 : << **Attacks that deal Flame Damage and Psychic Damage to enemies that are on hexes with Fire
deal +33% Damage.** Affected attacks from friendly Chaos units deal an additional +364 Damage. The
hex of each enemy that is hit by Ahriman's normal ranged attack catches Fire. >>
(les trois phrases = TROIS effets distincts ; seule la PREMIERE est `1215`.)

ARTEFACTS NATIFS (build rnca9r7q6c) :
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PsychicStalk_ExtraAttackDamageAbility$$CreateBehaviour`
      `AddEffect(0x4bf = 1215, <AbilityStateReference>, targets = Owner@0x30)
       + AddEffect(0x4c0 = 1216, ...) + AddEffect(0x59b = 1435, ...)`
      -> les TROIS effets vivent sur AHRIMAN, jamais sur la cible.
  - `IdunBattle.Entities.Effects.Loki.PsychicStalk_ExtraAttackDamageEffect$$CreateEffectDamageMalusForDefense`
      `EffectBonus.ForPercentIncrease(
             ( IsUnit(Caster@0x48) | IsMachine(Caster@0x48) | CasterIsCasterTile )
           & AreEnemies(Target@0x60, Owner@0x30)
           & GetTargetIsOnFireTileCondition() & GetAttackHasValidDamageProfileCondition(),
             ConfigVar(0xa = extraDmgPct, GetAbilityState(effet), config@+0x60) )`
      Le NOM dit << Malus...ForDefense >> (le slot d'interface = le canal DEFENSEUR), la FABRIQUE dit
      `ForPercentIncrease` : le degat RECU AUGMENTE. Ce n'est donc PAS le slot `flat_reductions` de
      son voisin `1110 FireAndReposition_ReduceDmg` (`ForSubtraction`) mais le **%-list DEFENSEUR**.
  - `IdunBattle.Entities.Effects.Loki.APsychicStalkEffect$$GetTargetIsOnFireTileCondition`
      `AmountIsEqualOrGreater( EntitiesWithAnyEffect(Tiles(Target@0x60), Fire = 5, effectTarget = 6),
                               <DSLFormulas+0x20 = Direct(1)> )`
  - `IdunBattle.Entities.Effects.Loki.APsychicStalkEffect$$GetAttackHasValidDamageProfileCondition`
      `DamageProfileIs([ GetAffectedDamageProfile() ?? 3 (Flame),
                         GetAffectedDamageProfile2() ?? 0xd (Psychic) ])`
  - CANAL consommateur : `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`,
      dont la boucle est GLOBALE (tous les effets ACTIFS de l'etat) -- d'ou le hook AURA
      `create_aura_defense_damage_malus_for_ally`, et non `create_effect_damage_malus_for_defense`
      (qui ne balaie que les effets de la CIBLE).

CE QUE CES GARDES TIENNENT, et qui n'est tenu nulle part ailleurs :
  * QUATRE gates, dont DEUX exerces LIVE et separement :
      - `GetTargetIsOnFireTileCondition` -> le bras SANS FEU doit rendre `live == port` SANS bonus,
        et le CONTREFACTUEL de tuile (feu eteint offline) doit rendre le degat non bonifie ;
      - `GetAttackHasValidDamageProfileCondition` / `AreEnemies` / le OU sur le caster -> exerces
        sur la vue d'effet (etage separe du degat).
  * L'ATTRIBUTION. `thousAhriman` porte DEUX AUTRES effets du meme kit, dont `1435` qui AJOUTE du
    degat au MEME coup. Le bras nominal choisit donc un attaquant ALLIE mais **NON-Chaos**
    (`astraPrimarisPsy`, arme PSYCHIC r2) : `1435` est muet (`HasTrait(Caster, 0x7ea = Chaos)`), et
    l'ecart mesure ne peut venir que de `1215`. L'ANTI-TEMOIN `--attacker ahriman` prouve que ce
    montage n'est pas un accord fortuit : quand `1435` tire, le port (qui ne le porte pas) DIVERGE.
  * Le NIVEAU. `ConfigVar(0xa)` s'indexe sur `GetAbilityState(effet)` ; l'`AbilityOrEffect` bake par
    la fabrique d'`EffectsDatabase` n'est PAS attribuable statiquement (corps de `.ctor` mutualise,
    cf. `reference_ctor_name_is_not_class_identity`). C'est le bras `--passive-level 1` qui TRANCHE :
    il dissocie le niveau PASSIF (25 %) de l'ACTIF (33 %), que `buildNormalizedBC` egalise a 50, et
    le CONTREFACTUEL DE NIVEAU montre que le regime discrimine.

Montage complet (build, drive des deux camps, pose du feu, captures, rejeux) :
`scripts/python/probe_366_r1_psychic_stalk.py`. ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_366_r1_psychic_stalk as PS

# Deux couples (board, seed) -- discipline de generalisation (runner.md S3) : un resultat obtenu
# sur UN seul board peut etre un artefact de sa geometrie (distances, spawns, terrain).
COUPLES = (("MC1_67", "31337"), ("C4_09", "4242"))


@pytest.fixture(scope="module")
def ps_case(live_session, rpc):
    """Fabrique : `ps_case(board, seed, attacker, passive_level)` -> le dict de mesure du probe.

    [!] Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un
    regime non atteint est un VERT qui ment -- aucune mesure n'a eu lieu."""
    cache: dict = {}

    def _case(board: str = "MC1_67", seed: str = "31337", attacker: str = "ally",
              passive_level: "int | None" = None) -> dict:
        k = (board, seed, attacker, passive_level)
        if k not in cache:
            r = PS.run(rpc, seed=seed, board_id=board, attacker=attacker,
                       passive_level=passive_level)
            if r.get("error"):
                pytest.fail("montage PsychicStalk NON INSTALLE (%s/%s/%s/lvl=%s): %s"
                            % (board, seed, attacker, passive_level, r["error"]))
            cache[k] = r
        return cache[k]
    return _case


def _assert_kit_posed(r):
    """E1 -- les TROIS effets du kit sont sur Ahriman, cote NATIF. Sans cette garde, un bras
    << port == live >> pourrait venir d'un kit absent, pas d'un gate correct."""
    assert r["e1_extra_inactive_channel"] is True, (
        "natif : `1215` ABSENT des effets d'Ahriman au deploiement -- le passif n'est pas monte, "
        "la mesure ne porte sur rien (effets vus : %s)" % (r["e1_effects_on_carrier"],))
    assert r["e1_chaos_inactive_channel"] is True, (
        "natif : `1435` absent -- l'ANTI-TEMOIN d'attribution n'a plus de sujet (%s)"
        % (r["e1_effects_on_carrier"],))
    assert r["e1_visual_inactive_channel"] is True, (
        "natif : `1216` absent (%s)" % (r["e1_effects_on_carrier"],))


def _assert_port_view(r, expected_pct):
    """Ce que le PORT materialise, AVANT tout calcul de degat -- etage separe : un port qui n'a PAS
    l'effet et un port dont le gate ferme rendraient le meme degat."""
    pv = r["b_port_effect_view"]
    assert pv.get("present") is True, (
        "le port ne materialise PAS 1215 sur la capture -- l'inscription `EFFECT_CLASSES` "
        "['PsychicStalk_ExtraAttackDamage'] manque (effets vus : %s)"
        % (pv.get("effects_on_carrier"),))
    assert pv.get("cls") == "PsychicStalkExtraAttackDamageEffect", (
        "1215 est route sur %s (attendu PsychicStalkExtraAttackDamageEffect)" % pv.get("cls"))
    assert pv.get("nominal") == ["PercentIncrease", expected_pct], (
        "port : bonus nominal = %s, attendu ['PercentIncrease', %s] = extraDmgPct[L%s]. "
        "`ForPercentIncrease` (%%-list DEFENSEUR), PAS `ForSubtraction`/`flat_reductions`."
        % (pv.get("nominal"), expected_pct, r["passive_level"]))
    assert pv.get("no_fire") is None, (
        "port : le gate `GetTargetIsOnFireTileCondition` ne ferme pas sur une tuile SANS feu "
        "(bonus rendu : %s)" % (pv.get("no_fire"),))
    assert pv.get("no_tile_channel") is None, (
        "port : canal d'effets de tuile ABSENT -> le port contribue quand meme (%s). La "
        "degradation doit etre << present != applique >>." % (pv.get("no_tile_channel"),))
    assert pv.get("profile_physical") is None, (
        "port : le gate `DamageProfileIs([Flame, Psychic])` laisse passer un profil Physical (%s)"
        % (pv.get("profile_physical"),))
    assert pv.get("profile_none") is None, (
        "port : profil NON THREADE -> le port contribue quand meme (%s)"
        % (pv.get("profile_none"),))
    assert pv.get("target_is_ally") is None, (
        "port : le gate `AreEnemies(Target@0x60, Owner@0x30)` laisse passer un ALLIE du porteur "
        "(%s)" % (pv.get("target_is_ally"),))
    assert pv.get("caster_unknown") is None, (
        "port : le OU `IsUnit|IsMachine|CasterIsCasterTile` ne ferme pas quand AUCUN des trois "
        "n'est threade (%s)" % (pv.get("caster_unknown"),))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_psychic_stalk_extra_damage_on_fire_tile_live(ps_case, board, seed):
    """Regime NOMINAL : cible ENNEMIE sur un hex EN FEU, coup PSYCHIC d'un allie NON-Chaos.
    Le port doit rendre le meme degat que le natif, ET la contre-epreuve doit montrer que l'effet
    y change quelque chose."""
    r = ps_case(board, seed)
    pct = r["extra_dmg_pct_passive"]
    print("\n[366-r1/1215 nominal %s/%s] %s" % (board, seed, {
        "pct": pct, "live": r["b_live_hits"], "port": r["b_port_hits"],
        "sans_1215": r["b_port_hits_without_effect"], "sans_feu": r["b_port_hits_without_fire"],
        "etage": r["b_stage_with"]}))

    assert pct, ("extraDmgPct irresoluble au niveau PASSIF %s -- la config d'ability a bouge ?"
                 % r["passive_level"])
    _assert_kit_posed(r)
    _assert_port_view(r, pct)

    assert r["b_target_on_fire"] is True, (
        "natif : la cible n'est PAS sur un hex en feu au moment du coup -- le regime n'est pas "
        "installe (hexes en feu : %s)" % (r["b_fire_tiles"],))
    assert not r["b_dirty"], "coup non propre (crit/block/evade) -- le bonus n'est pas isole"
    assert r["b_port_hits"] == r["b_live_hits"], (
        "port %s != natif %s (bonus attendu +%s%% sur les bornes)"
        % (r["b_port_hits"], r["b_live_hits"], pct))
    # CONTRE-EPREUVE de discriminance : sans l'effet, MEME capture, MEME flux MT.
    assert r["b_port_hits_without_effect"] != r["b_port_hits"], (
        "regime NON DISCRIMINANT : retirer 1215 ne change RIEN au degat (%s) -- la mesure ne "
        "prouve rien" % (r["b_port_hits"],))
    # ETAGE : le canal ecrit dans le %-list DEFENSEUR, pas dans l'additif ni les flat_reductions.
    st = r["b_stage_with"]
    assert [round(m, 4) for m, _c in st["pct_list"]] == [round(1 + pct / 100.0, 4)], (
        "port : le %%-list DEFENSEUR vaut %s, attendu [%s] -- le canal n'ecrit pas dans le bon slot"
        % (st["pct_list"], 1 + pct / 100.0))
    assert st["flat_reductions"] == [] and st["additive"] == 0, (
        "port : le canal a ecrit dans `flat_reductions`/`additive` (%s / %s) -- c'est le slot de "
        "`ForSubtraction`/`ForAddition`, pas celui de `ForPercentIncrease`"
        % (st["flat_reductions"], st["additive"]))
    assert r["b_stage_without"]["pct_list"] == [], (
        "port : le %%-list DEFENSEUR n'est PAS vide sans 1215 (%s) -- une autre source contribue, "
        "l'attribution du bras est cassee" % (r["b_stage_without"]["pct_list"],))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_psychic_stalk_fire_tile_gate_live(ps_case, board, seed):
    """Le gate `GetTargetIsOnFireTileCondition`, exerce des DEUX bouts :

      * LIVE -- au tour 1 la cible n'est sur AUCUN hex en feu ; l'effet est pourtant PRESENT sur
        Ahriman. Le natif ne bonifie pas, le port non plus (`live == port`).
      * OFFLINE -- CONTREFACTUEL de tuile sur la capture du tour 2 : on eteint le feu sous la cible,
        le port doit alors rendre EXACTEMENT le degat sans l'effet.
    Les deux voies ferment le MEME gate ; qu'elles coincident est ce qui prouve qu'il est PORTEUR."""
    r = ps_case(board, seed)
    print("\n[366-r1/1215 gate-feu %s/%s] %s" % (board, seed, {
        "a_feu_sous_cible": r["a_target_on_fire"], "a_live": r["a_live_hits"],
        "a_port": r["a_port_hits"], "e3_hexes_en_feu": r["e3_fire_tiles"],
        "b_port": r["b_port_hits"], "b_sans_feu": r["b_port_hits_without_fire"],
        "b_sans_1215": r["b_port_hits_without_effect"]}))

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
    # CONTREFACTUEL de tuile == contre-epreuve d'effet : le MEME gate, ferme par deux bouts.
    assert r["b_port_hits_without_fire"] == r["b_port_hits_without_effect"], (
        "port : eteindre le feu (%s) et retirer 1215 (%s) ne donnent PAS le meme degat -- le gate "
        "`GetTargetIsOnFireTileCondition` n'est pas le seul chemin par lequel l'effet contribue"
        % (r["b_port_hits_without_fire"], r["b_port_hits_without_effect"]))
    assert r["b_port_hits_without_fire"] != r["b_port_hits"], (
        "le contrefactuel de tuile ne CHANGE rien (%s) : la mesure ne discrimine pas"
        % (r["b_port_hits"],))


def test_psychic_stalk_magnitude_indexed_by_passive_level(ps_case):
    """DISCRIMINANT de NIVEAU. `--unit-stat "thousAhriman:PassiveAbilityLevel=1"` dissocie le PASSIF
    de l'ACTIF (que `buildNormalizedBC` egalise a 50) : c'est le SEUL regime qui distingue les deux
    lectures possibles de `GetAbilityState(effet)`, que la RE ne peut PAS trancher statiquement
    (le `.ctor` de `PsychicStalk_ExtraAttackDamageEffect` n'existe pas dans les tables -- corps
    mutualise avec `APsychicStalkEffect$$.ctor`, qui prend son `AbilityOrEffect` en PARAMETRE).

    MESURE (C4_09/4242, passif 1 / actif 50) : natif [3029] = extraDmgPct[L1] = 25 % ; le meme
    rejeu force au niveau ACTIF (33 %) donnerait [3684]. Le regime discrimine donc bien, et c'est
    le PASSIF qui est lu."""
    r = ps_case("C4_09", "4242", "ally", 1)
    pct_p, pct_a = r["extra_dmg_pct_passive"], r["extra_dmg_pct_active"]
    print("\n[366-r1/1215 niveau-passif] %s" % ({
        "passif": r["passive_level"], "actif": r["active_level"],
        "pct_passif": pct_p, "pct_actif": pct_a, "live": r["b_live_hits"],
        "port": r["b_port_hits"], "port_si_actif": r["b_port_hits_active_level"]},))

    assert r["passive_level"] == 1, (
        "le patch `PassiveAbilityLevel=1` n'a pas pris (combatSnapshot expose L%s) -- le regime "
        "n'est pas installe, la mesure ne discrimine rien" % (r["passive_level"],))
    assert r["passive_level"] != r["active_level"], (
        "passif == actif == %s : regime NON DISCRIMINANT" % (r["passive_level"],))
    assert pct_p != pct_a, (
        "extraDmgPct[passif L%s] == extraDmgPct[actif L%s] == %s : les deux niveaux tombent sur la "
        "MEME valeur de config -- choisir un autre niveau"
        % (r["passive_level"], r["active_level"], pct_p))
    _assert_kit_posed(r)
    _assert_port_view(r, pct_p)
    assert not r["b_dirty"], "coup non propre (crit/block/evade)"
    assert r["b_port_hits"] == r["b_live_hits"], (
        "port %s != natif %s -- si l'ecart vaut celui du niveau ACTIF (%s), c'est l'AbilityState de "
        "l'ACTIVE que le natif resout, pas celle du PASSIF"
        % (r["b_port_hits"], r["b_live_hits"], r["b_port_hits_active_level"]))
    # CONTREFACTUEL DE NIVEAU : sans lui, << live == port >> ne prouverait rien si les deux niveaux
    # donnaient la meme valeur tiree.
    assert r["b_port_hits_active_level"] != r["b_port_hits"], (
        "le contrefactuel de niveau ACTIF rend le MEME degat (%s) : le regime ne discrimine pas "
        "les deux lectures" % (r["b_port_hits"],))


def test_psychic_stalk_attribution_anti_witness(ps_case):
    """ANTI-TEMOIN d'ATTRIBUTION. Le bras nominal choisit un attaquant NON-Chaos pour faire taire
    `1435 PsychicStalk_FriendlyChaosExtraDamage` (`ForAddition(AreFriends(Owner, Caster) &
    HasTrait(Caster, 0x7ea = Chaos) & <les 2 conditions partagees>, ConfigVar(8 = extraDmg))`).
    Ce test joue le bras INVERSE -- Ahriman frappe lui-meme, donc `1435` tire AUSSI -- et exige que
    le port DIVERGE : c'est ce qui prouve que l'accord du bras nominal n'est pas fortuit, et que
    `1435` est bien un residu NON PORTE et non un effet inerte.

    MESURE (MC1_67/31337) : live [4253] vs port [3589], ecart 664 = round(extraDmg[L50] x 1.8 x 1.33)
    = l'additif ATTAQUANT de `1435` (499 pre-percage) scale par le %-list DEFENSEUR de `1215`.
    Le bras SANS FEU, lui, CONCORDE (les deux effets partagent `GetTargetIsOnFireTileCondition`)."""
    r = ps_case("MC1_67", "31337", "ahriman")
    print("\n[366-r1/1215 anti-temoin] %s" % ({
        "a_live": r["a_live_hits"], "a_port": r["a_port_hits"],
        "b_live": r["b_live_hits"], "b_port": r["b_port_hits"],
        "b_sans_1215": r["b_port_hits_without_effect"]},))

    _assert_kit_posed(r)
    assert r["b_target_on_fire"] is True, "regime non installe (cible hors hex en feu)"
    assert not r["b_dirty"], "coup non propre (crit/block/evade)"
    # SANS FEU : les DEUX effets sont muets (condition partagee) -> le port doit CONCORDER.
    assert r["a_port_hits"] == r["a_live_hits"], (
        "bras SANS FEU : port %s != natif %s alors que `1215` ET `1435` sont muets -- une autre "
        "divergence pollue le montage" % (r["a_port_hits"], r["a_live_hits"]))
    # AVEC FEU : `1435` tire, le port ne le porte pas -> il DOIT diverger.
    assert r["b_port_hits"] != r["b_live_hits"], (
        "port %s == natif %s alors que `1435` (non porte) devrait AJOUTER son extraDmg : soit le "
        "bras nominal mesurait deja une somme des deux effets, soit `1435` est inerte -- dans les "
        "deux cas l'attribution du cas est fausse" % (r["b_port_hits"], r["b_live_hits"]))
    deltas = {b - a for a, b in zip(r["b_port_hits"], r["b_live_hits"])}
    assert all(d > 0 for d in deltas), (
        "l'ecart de l'anti-temoin est NEGATIF (%s) : le port SUR-predit, ce n'est pas la signature "
        "d'un effet additif manquant" % (sorted(deltas),))
