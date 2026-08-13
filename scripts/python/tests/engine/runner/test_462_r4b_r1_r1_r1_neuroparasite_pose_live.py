"""#462-r4b-r1-r1-r1 -- la POSE de `Neuroparasite` et sa MONTEE EN NIVEAU, confrontees en COMBAT.

#462-r4b-r1-r1 (PR #553) a ferme la MAGNITUDE de l'additif defenseur du parasite (port 4448 == natif
4448). Mais son §8 nommait le residu : **la POSE n'etait pas portee**. La mesure n'avait ete possible
que parce que le parasite venait du NATIF et que l'etat etait SEEDE -- en self-play 100 % porte, il
n'apparaissait JAMAIS, et tous les bras etaient au NIVEAU 1 (`GetIncreaseLevelBehaviour` non portee
non plus). Un effet dont la magnitude est juste mais que rien ne pose est un canal MORT.

TROIS BRAS, ET CHACUN SEPARE PAR UN GATE DIFFERENT :

  * `pose`   -- l'attaque PSYCHIQUE du Neurothrope pose 1218 sur sa cible, cote PORT comme cote
                NATIF, avec l'etat BAKE (`bonded` = le Neurothrope, `ability_level` = le niveau de
                SON passif). Puis une SECONDE attaque psychique fait monter le parasite de 1 a 2 des
                deux cotes, sous le cap `GetMaximumLevel` = `buffMaxLevel[lvl]`. Enfin, le degat de
                cette 2e attaque doit rester CELUI QU'A ATTESTE #553 -- c'est la non-regression la
                plus forte du lot : elle prouve que la POSE portee ne deplace pas la magnitude.
  * `melee`  -- CONTROLE NEGATIF. Le Neurothrope est bi-arme (melee `Physical`, ranged `Psychic`
                portee 3). AU CONTACT il frappe en `Physical` : le gate
                `CurrentAttackDamageProfilesContain(0xd)` ne s'ouvre pas et AUCUN parasite ne doit
                etre pose, ni par le port ni par le natif. C'est le SEUL regime qui separe le port
                d'un port qui aurait oublie ce gate.
  * `pinned` -- la SECONDE voie de montee, celle du 2e `Triggered()` :
                `On(0x3d = PreEffectAdded) & OwnerIsTarget & TriggeringEffectIs(0x429 = 1065 Pinned)`.
                `templAggressor` (trait `SuppressiveFire`) frappe la cible parasitee avec son
                `Bolter` -- une arme RANGED **NON psychique**. Le Pinned pose fait monter le parasite
                de 1 a 2. DISCRIMINANT : le profil `Bolter` ferme le gate de l'AUTRE trigger, donc un
                port qui aurait oublie ce gate rendrait **3** au lieu de 2.

BORNE ASSERTIONNEE (et non une confirmation) : `Psychic` a `PiercingRatio = 100`, donc le plancher
`max(d x pierce%, d - armure)` est l'IDENTITE et l'axe PERCAGE est STRUCTURELLEMENT ferme a ce
carrier, quelle que soit l'armure. Rien de ce qui est mesure ici ne dit quoi que ce soit du
PLACEMENT de l'additif -- cet axe-la est garde par
`test_462_r4b_r1_r1_defender_additive_carriers_live.py`, et par lui seul.

Montage : `probe_462_r4b_r1_r1_r1_neuroparasite_pose.py` (ce fichier n'en est que la porte pytest).
ASCII only. Dispose SES runners.
"""
from __future__ import annotations

import pytest

import probe_462_r4b_r1_r1_r1_neuroparasite_pose as PB

NEUROPARASITE = 1218               # l'EFFET (1183 est le `TriggeredAbilityType` homonyme)
PINNED = 1065                      # `EffectType.Pinned` -- pose par le trait `SuppressiveFire`
#: Degat de la 2e attaque. ⚠ CE SCALAIRE DEPEND DU REGIME D'EQUIPEMENT, et il a ete regrave --
#: mesure du 2026-08-13, sur le MEME arbre, meme montage, seule la bascule change :
#:
#:     TACTICUS_BIS_ITEMS defaut (items Best-In-Slot)  ->  port 4677 == live 4677
#:     TACTICUS_BIS_ITEMS=0       (regime DEGENERE)    ->  port 4448 == live 4448   (7 passed)
#:
#: `4448` etait la valeur ATTESTEE par #462-r4b-r1-r1 (PR #553), ecrite AVANT la bascule #419-r5 --
#: c'est le vice de #914-r2 (« toute premisse de montage ecrite AVANT cette bascule est suspecte »),
#: sous sa forme SCALAIRE. Ce que le rouge accusait n'etait donc PAS le port : `port == live` dans
#: les DEUX regimes, l'accord n'a jamais ete rompu. Re-graver le nombre est la reparation ; faire
#: diverger le port pour satisfaire une attestation morte aurait ete la faute.
#: ⚠ Le cliquet `tests/engine/test_933_premisse_regime_offline.py` ne voit PAS cette forme : il
#: cherche une premisse de regime ECRITE dans une docstring, pas un SCALAIRE grave. Residu #933-r3.
NEURO_ATTACK2 = 4677               # regime BiS (defaut), mesure 2026-08-13 ; 4448 = regime BIS=0
BUFF_MAX_LEVEL_50 = 15             # `ConfigVar(0x4c = buffMaxLevel)` au niveau de passif 50


@pytest.fixture(scope="module")
def pose_case(live_session):
    m = PB.measure(live_session)
    if m.get("skip"):
        pytest.skip(m["skip"])
    return m


@pytest.fixture(scope="module")
def melee_case(live_session):
    m = PB.measure_melee_negative(live_session)
    if m.get("skip"):
        pytest.skip(m["skip"])
    return m


@pytest.fixture(scope="module")
def pinned_case(live_session):
    m = PB.measure_pinned_level(live_session)
    if m.get("skip"):
        pytest.skip(m["skip"])
    return m


# ------------------------------------------------------------------ (1) la POSE

def test_le_port_POSE_le_parasite_comme_le_natif(pose_case):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.NeuroparasiteAbility$$CreateBehaviour` =
    `AddBondEffect(0x4c2, abilityState, source: Owner, targets: Target, bondedEntity: Owner,
    options: <vide>)`, arme par `$$CreateTrigger` sur `On(9 = Attack)`.

    AVANT ce port, `port_pose_count` valait 0 alors que le natif rendait 1 : le parasite n'existait
    offline QUE parce que le seed le recopiait de l'etat natif."""
    m = pose_case
    assert m["pre_port_parasites"] == 0 and m["pre_live_parasite"] is False, (
        "l'etat de depart porte deja un parasite -> le bras ne mesure pas une POSE (%s / %s)"
        % (m["pre_port_parasites"], m["pre_live_parasite"]))
    assert m["port_attack1_profile"] == "Psychic", (
        "profil %s -- le montage a bascule sur l'arme melee, le gate ne peut pas s'ouvrir"
        % (m["port_attack1_profile"],))
    assert m["live_pose"]["present"] is True, "le NATIF n'a pas pose le parasite"
    assert m["port_pose_count"] == 1, (
        "le PORT a pose %s parasite(s), le natif 1 -- une POSE non portee est un canal MORT en "
        "self-play, exactement le residu que ce cas ferme" % (m["port_pose_count"],))
    assert m["port_pose"]["level"] == m["live_pose"]["level"] == 1, (
        "niveau initial port=%s natif=%s" % (m["port_pose"]["level"], m["live_pose"]["level"]))


def test_l_etat_BAKE_a_la_pose_est_celui_du_NEUROTHROPE(pose_case):
    """Le 3e argument natif d'`AddBondEffect` est l'`AbilityStateReference` du PORTEUR : l'entite-
    effet BAKE le niveau d'ability + le multiplier du Neurothrope, et c'est CE couple que relit
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` dans `$$GetMaximumLevel`.

    Le 5e argument (`bondedEntity`, `Owner@0x30`) est ce que relit
    `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId` -- donc le gate
    `AreEqual(BondedEntity, damageSource)` de l'additif de degat. Sans lui, l'additif ne saurait pas
    distinguer le Neurothrope d'un autre psyker."""
    m = pose_case
    p = m["port_pose"]
    assert p["cls"] == "NeuroparasiteEffect", (
        "l'effet pose n'est pas route vers sa classe portee (%s)" % (p["cls"],))
    assert p["bonded"] == m["neuro"] and p["source"] == m["neuro"], (
        "bonded=%s source=%s, attendu le Neurothrope u%s" % (p["bonded"], p["source"], m["neuro"]))
    assert p["ability_level"] is not None, (
        "`ability_level` non bake -> `GetMaximumLevel` n'a pas de niveau a indexer (le 3e argument "
        "natif `abilityState` d'AddBondEffect n'est pas transporte)")
    assert p["remaining"] is None, (
        "duree %s : les options natives sont VIDES -> `DefaultAmountOfRounds(0x4c2)` absente -> "
        "PERMANENT (`remaining = 0` cote operation, `None` cote instance)" % (p["remaining"],))


# ------------------------------------------------------------------ (2) la MONTEE EN NIVEAU

def test_le_parasite_MONTE_d_un_cran_a_chaque_frappe_psychique(pose_case):
    """1er `Triggered()` de `NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal` :
    `On(9) & OwnerIsTarget & CurrentAttackDamageProfilesContain(0xd)` ->
    `IncreaseEffectLevel(Effect, Direct(1), GetMaximumLevel())`.

    Sans lui tout parasite restait a 1 -- or l'additif de degat est `x EffectLevel` : le port aurait
    plafonne a un cran quand le natif en accumule jusqu'a `buffMaxLevel`."""
    m = pose_case
    assert m["t2_port_level_before"] == m["t2_live_level_before"] == 1, (
        "niveau avant la 2e attaque port=%s natif=%s"
        % (m["t2_port_level_before"], m["t2_live_level_before"]))
    assert m["t2_port_level_after"] == 2, (
        "le PORT n'a pas monte le niveau (%s) -- `GetIncreaseLevelBehaviour` non armee"
        % (m["t2_port_level_after"],))
    assert m["t2_live_level_after"] == 2, "le NATIF n'a pas monte le niveau (%s)" % (
        m["t2_live_level_after"],)


def test_le_cap_GetMaximumLevel_vaut_buffMaxLevel(pose_case):
    """`$$GetMaximumLevel` = `Sum(ConfigVar(0x4c = buffMaxLevel, GetAbilityState(effect)),
    If(ActorHasTriggeredAbility(BondedEntity, 0x5d7 = NornCrown), ConfigConst(0x73 = effectLevel),
    Direct(0)))`.

    `0x4c` est QUALIFIE par EXCLUSION sur la config REELLEMENT SERVIE : `BC.Abilities.
    PassiveAbilities.Neuroparasite.Variables` n'a que DEUX entrees, `extraDmg` (index 8, atteste
    bit-exact) et `buffMaxLevel`. Ici le Neurothrope ne porte pas `NornCrown` -> le terme
    conditionnel vaut 0 et le cap est `buffMaxLevel[50] = 15`.

    ⚠ Le cap n'est pas CONFRONTE (il faudrait 15 frappes pour qu'il morde) : ce test verifie la
    VALEUR que le port calcule, pas le clamp lui-meme -- lequel est celui, deja porte et teste,
    d'`IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute`."""
    m = pose_case
    assert m["t2_port_max_level"] == BUFF_MAX_LEVEL_50, (
        "cap calcule %s, attendu %s (`buffMaxLevel[50]`) -- un `None` signifie que l'etat d'ability "
        "n'est pas bake sur l'instance" % (m["t2_port_max_level"], BUFF_MAX_LEVEL_50))


def test_la_pose_portee_ne_deplace_PAS_la_magnitude_attestee(pose_case):
    """NON-REGRESSION la plus forte du lot : la 2e attaque doit rendre EXACTEMENT `NEURO_ATTACK2`.
    Le parasite y est encore au niveau 1 au moment ou l'additif est lu -- la montee a 2 n'a lieu
    qu'a la CLOTURE (`On(9)`), APRES le degat.

    Si ce test rougissait au DOUBLE (`2 x NEURO_ATTACK2`), le port aurait monte le niveau AVANT de
    resoudre le degat : une inversion d'ordre que seul ce chiffre revele. C'est pour ce cran que la
    valeur est ecrite en dur et non re-derivee -- mais elle depend du REGIME D'EQUIPEMENT, d'ou les
    deux mesures citees sur `NEURO_ATTACK2`.

    ⚠ LA PREMIERE ASSERTION EST CE QUI SEPARE LES DEUX ACCUSES. `port == live` dit que le port suit
    le natif ; c'est seulement APRES elle que la seconde confronte le nombre GRAVE. Un rouge de la
    seconde SEULE accuse l'attestation, jamais le port -- c'est exactement ce qui est arrive le
    2026-08-13 (`port=4677 live=4677 attendu 4448`)."""
    m = pose_case
    assert m["port_attack2_per_hit"] == m["live_attack2_per_hit"], (
        "ledger PAR COUP divergent\n  port=%s\n  live=%s"
        % (m["port_attack2_per_hit"], m["live_attack2_per_hit"]))
    assert m["port_attack2_total"] == m["live_attack2_delta"] == NEURO_ATTACK2, (
        "port=%s live=%s attendu %s (attestation #462-r4b-r1-r1)"
        % (m["port_attack2_total"], m["live_attack2_delta"], NEURO_ATTACK2))


# ------------------------------------------------- (3) le CONTROLE NEGATIF du gate de profil

def test_une_attaque_MELEE_ne_pose_AUCUN_parasite(melee_case):
    """Le gate `CurrentAttackDamageProfilesContain(0xd = Psychic)` dans les DEUX sens. Amene au
    CONTACT, le Neurothrope frappe avec son arme melee `Physical` : ni le port ni le natif ne posent.

    Sans ce bras, un port sans gate de profil rendrait exactement les memes chiffres que le bras
    nominal -- l'accord y serait donc sans valeur."""
    m = melee_case
    assert m["port_profile"] == "Physical", (
        "profil %s -- le montage n'a pas bascule sur l'arme melee, le controle negatif ne controle "
        "rien" % (m["port_profile"],))
    assert m["port_parasites"] == 0, (
        "le PORT a pose %s parasite(s) sur une attaque NON psychique -- le gate de profil manque"
        % (m["port_parasites"],))
    assert m["live_parasite"] is False, "le NATIF a pose un parasite en melee (RE a revoir)"


# ------------------------------------------- (4) la SECONDE voie de montee : `On(PreEffectAdded)`

def test_un_Pinned_pose_sur_la_victime_fait_monter_le_parasite(pinned_case):
    """2e `Triggered()` : `On(0x3d = PreEffectAdded) & OwnerIsTarget & TriggeringEffectIs(0x429)`.

    `templAggressor` (trait `SuppressiveFire`) frappe la cible parasitee avec son `Bolter`. Le trait
    pose `Pinned`, dont la POSE emet `On(0x3d)` avec le canal `TriggeringAbility` renseigne
    (asymetrie #306 : au RETRAIT il ne le serait pas) -> le parasite monte de 1 a 2.

    DISCRIMINANT : `Bolter` n'est PAS psychique, donc le gate de l'AUTRE trigger (`On(9)`) reste
    ferme. Un port qui l'aurait oublie rendrait 3."""
    m = pinned_case
    assert m["level_after_psychic_live"] == 1, (
        "le montage ne part pas d'un parasite au niveau 1 (%s)" % (m["level_after_psychic_live"],))
    assert m["port_profile"] not in (None, "Psychic"), (
        "l'attaque du pinner est %s -- si elle etait psychique les DEUX triggers mordraient et le "
        "bras ne serait plus discriminant" % (m["port_profile"],))
    assert PINNED in m["live_effect_types"], (
        "`Pinned` (1065) absent de la cible cote natif -> aucun `On(0x3d)` qualifiant n'a ete emis "
        "(effets=%s)" % (m["live_effect_types"],))
    assert m["port_level_after"] == 2, (
        "niveau port %s -> %s ; attendu 2 (le trigger `On(0x3d)` n'a pas mordu, ou les DEUX ont "
        "mordu)" % (m["port_level_before"], m["port_level_after"]))
    assert m["live_level_after"] == 2, "niveau natif %s, attendu 2" % (m["live_level_after"],)
