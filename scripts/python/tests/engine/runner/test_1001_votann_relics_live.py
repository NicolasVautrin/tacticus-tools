"""GARDE LIVE #1001 -- les DEUX reliques LEAGUES OF VOTANN, confrontees au natif.

  * `BladeOfTheAncestors`   (1491, `votanUthar`)   : buff crit EMPILABLE + RESET DIFFERE au crit ;
  * `VolummsMasterArtifice` (1488, `votanIronmaster`) : compteur de reparations + SOIN au seuil.

Ce que ces gardes exigent, et de quel artefact :
  * la MAGNITUDE est indexee sur le couple TERTIAIRE (`TertiaryAbilityLevel` /
    `TertiaryAbilityVariablesMultiplierPercentage`, #357) -- les deux montages tournent au niveau
    **3**, le seul ou le palier demande differe du palier CLAMPE que rendrait une lecture du niveau
    des PASSIFS (50) ;
  * le RESET du buff crit passe par la FILE des triggered-abilities differees (#406) :
    `TriggerAbilityDelayed(Owner, 1491, 3)` sur `On(9) & WasCrit`, puis la branche `Custom` au
    drain. Un collapse INLINE retirerait le buff AU MILIEU de la salve ;
  * le SEUIL de Vynn porte sur le compteur DEJA incremente (`>= nrOfRepairs`), l'INVERSE de
    `DaemonfleshPlate`.

Montage : `probe_1001_votann_relics.py`. Les volets `blade`/`reset` montent leur propre runner et
le DISPOSENT ; le volet `volumm` conduit en plus une dizaine de tours (une reparation par tour),
donc il est LENT -- c'est le prix du seul temoin NON DEGENERE du seuil.

⚠ Le volet `volumm` RETIRE `EcogSupport` des passifs de Vynn : sans ce retrait, les E-COGs
reparent tout seuls pendant le tour de leur equipe et le RANG du franchissement devient
incomptable. La greffe est declaree (`declare_graft`). ASCII only.
"""
from __future__ import annotations

#: LIVE : le verdict depend du NATIF, donc de la session et du build -- aucun ensemble de chemins du
#: depot ne le determine. `toujours: True` est ici un RESULTAT, pas un aveu : ce fichier doit se
#: rejouer des qu'une session tourne, y compris quand rien du port n'a bouge (un changement de build
#: peut renumeroter les paliers ou deplacer un gate natif). Les chemins listes sont ceux dont une
#: modification SUFFIT a changer le verdict sans changer le natif.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_1001_votann_relics.py",
        "scripts/python/engine/runner/operations/triggers/loki/blade_of_the_ancestors.py",
        "scripts/python/engine/runner/operations/triggers/loki/volumms_master_artifice.py",
        "scripts/python/engine/entities/effects/loki/votann.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/pending.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/repair.py",
        "scripts/python/catalog_inject.py",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": True,
    "raison": "Confrontation AU NATIF : les deux reliques sont montees par injection catalogue + "
              "`--equip-relic`, et les verdicts (delta de stats crit, rang et montant du soin) "
              "sortent du jeu, pas du depot. Se rejoue donc a chaque passe live.",
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

import probe_1001_votann_relics as P                                          # noqa: E402
from engine.entities.effects.magnitude import ability_var                     # noqa: E402

LEVEL = 3


def _var(ability: str, key: str, level: int) -> int:
    return int(ability_var(ability, key, level, multiplier_pct=100) or 0)


@pytest.fixture(scope="module")
def blade_case(rpc):
    """Fabrique : `blade_case()` / `blade_case(reset=True)` -> le dict de mesure du volet BLADE.

    Le runner est monte ET dispose PAR LE PROBE (`keep=False`) : chaque bras est un build, une
    conduite de positions et un kill reel. Portee MODULE.
    ⚠ Montage non installe => ECHEC, jamais skip (#268)."""
    cache: dict = {}

    def _case(reset: bool = False) -> dict:
        if reset not in cache:
            r = P.run_blade(rpc, level=LEVEL, reset=reset)
            if not r.get("ok"):
                pytest.fail("montage BladeOfTheAncestors NON INSTALLE (reset=%s) : %s"
                            % (reset, r.get("why")))
            cache[reset] = r
        return cache[reset]

    return _case


@pytest.fixture(scope="module")
def volumm_case(rpc):
    """Fabrique : `volumm_case()` -> le dict de mesure du volet VOLUMM (10 reparations conduites)."""
    cache: dict = {}

    def _case(repairs: int = 10) -> dict:
        if repairs not in cache:
            r = P.run_volumm(rpc, level=LEVEL, repairs=repairs, no_ecog=True)
            if not r.get("ok"):
                pytest.fail("montage VolummsMasterArtifice NON INSTALLE : %s" % (r.get("why"),))
            cache[repairs] = r
        return cache[repairs]

    return _case


# --------------------------------------------------------------------------- BLADE : la POSE
def test_blade_le_natif_et_le_port_posent_le_meme_buff_crit(blade_case):
    """L'ACCORD sur les DEUX stats : natif == port == (`extraCritChance[3]`, `extraCritDmg[3]`).

    On ne mesure AUCUN jet de critique -- on lit les STATS, que `combatSnapshot` rend par
    `IdunBattle.Entities.UnitExtensions$$GetStat`."""
    r = blade_case()
    exp_cc, exp_cd = _var(P.BLADE, "extraCritChance", LEVEL), _var(P.BLADE, "extraCritDmg", LEVEL)
    assert exp_cc > 0 and exp_cd > 0, "variables introuvables dans le gameconfig de %s" % P.BLADE
    assert r["victim_dead"], (
        "la victime n'est pas morte : sans kill, `On(UnitDeath)` n'est jamais emis et la mesure ne "
        "porte sur rien (%s)" % (r.get("attack_ack"),))
    assert r["mounted"]["abilityId"] == P.BLADE_ID and r["mounted"]["level"] == LEVEL, (
        "l'entree de hierarchie 3 lue n'est pas celle attendue : %s" % (r["mounted"],))
    assert r["native_delta"] == {"cc": exp_cc, "cd": exp_cd}, (
        "NATIF : delta %s, attendu %s" % (r["native_delta"], {"cc": exp_cc, "cd": exp_cd}))
    assert (r["port"]["cc_delta"], r["port"]["cd_delta"]) == (exp_cc, exp_cd), (
        "PORT : delta (%s, %s), attendu (%d, %d)"
        % (r["port"]["cc_delta"], r["port"]["cd_delta"], exp_cc, exp_cd))
    assert r["port"]["stacks"] == 1, "une seule pile pour un seul kill, lu %s" % r["port"]["stacks"]


def test_blade_le_natif_materialise_bien_l_effet_1489(blade_case):
    """L'effet `BladeOfTheAncestors_Effect` (0x5d1 = 1489) est CAPTE sur le porteur cote natif --
    c'est ce qui etablit que le buff est bien un EFFET-entite (donc que `EFFECT_CLASSES` est le bon
    canal), et pas un stat-mod pose a la volee."""
    r = blade_case(reset=True)          # le bras `reset` est celui dont on lit `decisionView` apres
    noms = {e.get("name") for e in (r.get("native_effects") or [])}
    assert "BladeOfTheAncestors_Effect" in noms, (
        "aucun effet 1489 sur le porteur cote natif : %s" % sorted(noms))


def test_blade_sans_le_rail_le_port_est_inerte(blade_case):
    """CONTRE-EPREUVE 1 -- l'etat d'AVANT #357, rejoue sur LA MEME capture. Sans ce bras, le test
    nominal serait un vert que rien ne fait rougir."""
    r = blade_case()
    assert r["port"]["tertiary"] == P.BLADE, (
        "le canal ne seede pas `UnitContext.tertiary_ability` (lu : %s)" % r["port"]["tertiary"])
    assert r["port_no_rail"]["tertiary"] is None
    assert (r["port_no_rail"]["stacks"], r["port_no_rail"]["cc_delta"],
            r["port_no_rail"]["cd_delta"]) == (0, 0, 0), (
        "sans le canal #357 le port ne doit RIEN poser, or il rend %s" % (r["port_no_rail"],))
    assert r["native_delta"]["cd"] > 0, "le natif, lui, buffe -- c'est bien un ECART que le rail ferme"


def test_blade_le_niveau_lu_est_le_TERTIAIRE_pas_celui_des_passifs(blade_case):
    """CONTRE-EPREUVE 2 -- sur l'axe MAGNITUDE. `passive_ability_level` vaut 50 sur tout runner
    normalise et `TryGetVariableArrayForLevel` CLAMPE : lire le mauvais slot rendrait TOUJOURS
    `extraCritDmg[10]`. Le bras mute doit DIVERGER du natif."""
    r = blade_case()
    exp, clamped = _var(P.BLADE, "extraCritDmg", LEVEL), _var(P.BLADE, "extraCritDmg", 50)
    assert clamped != exp, "le niveau %d ne separe RIEN -- changer de bras" % LEVEL
    assert r["port"]["level"] == LEVEL
    assert r["port_passive_level"]["cd_delta"] == clamped, (
        "le bras mute devrait rendre le palier CLAMPE %d, il rend %s"
        % (clamped, r["port_passive_level"]["cd_delta"]))
    assert r["port_passive_level"]["cd_delta"] != r["native_delta"]["cd"], (
        "la contre-epreuve ne rougit pas : le niveau des PASSIFS donne le meme resultat que le "
        "natif au niveau %d -- le montage ne separe pas les deux champs" % LEVEL)


# --------------------------------------------------------------------------- BLADE : le RESET
def test_blade_le_crit_du_porteur_efface_le_buff_des_DEUX_cotes(blade_case):
    """`On(9) & OwnerIsCaster & WasCrit & HasEffect(Owner, 1489)` -> le buff tombe, natif ET port.

    Le porteur crite sur une cible qui SURVIT : un kill par Uthar ajouterait une pile (branche 2 du
    `CreateTrigger`) et melangerait les deux mesures. La chance de crit est PLAFONNEE a 100 dans ce
    bras (`GetClampedValue`), donc seul `critDamage` est lisible -- et c'est lui qu'on suit."""
    r = blade_case(reset=True)
    exp_cd = _var(P.BLADE, "extraCritDmg", LEVEL)
    assert r["survivor_alive"], (
        "la 2e cible est morte : le kill aurait ajoute une pile en plus du reset")
    assert r["native_delta"]["cd"] == exp_cd, (
        "la pose n'a pas eu lieu dans ce bras : %s" % (r["native_delta"],))
    assert r["reset_delta"]["cd"] == -exp_cd and r["cd_back_to_base"], (
        "NATIF : apres le crit, `critDamage` bouge de %s (attendu %d) -- retour a la base = %s"
        % (r["reset_delta"]["cd"], -exp_cd, r.get("cd_back_to_base")))
    p = r["port"]["reset"]
    assert p is not None and p["cd_delta"] == -exp_cd and p["cd_back_to_base"], (
        "PORT : le reset rend %s, attendu %d" % (p, -exp_cd))
    assert p["stacks_left"] == 0, "le `RemoveEffect` doit retirer TOUTES les piles"


def test_blade_le_reset_passe_par_la_FILE_et_pas_par_un_retrait_immediat(blade_case):
    """LE POINT PORTEUR DE LA TRANCHE. `CreateBehaviour` fourche sur `triggerType` : `!= Custom` ->
    `TriggerAbilityDelayed`, `== Custom` -> `RemoveEffect`. Le port doit donc ENFILER puis retirer
    AU DRAIN -- sinon le buff tomberait au milieu de la salve au lieu d'a sa fin."""
    r = blade_case(reset=True)
    p = r["port"]["reset"]
    assert p["queued"] and p["queued"][0]["queued"] and p["queued"][0]["dispatched"], (
        "le vecteur `On(9)` doit ENFILER (`queued`), pas retirer sur place : %s" % (p["queued"],))
    assert p["drained"] and p["drained"][0]["removed"] >= 1, (
        "le drain de `pending_triggered_abilities` doit executer la branche `Custom` : %s"
        % (p["drained"],))


# --------------------------------------------------------------------------- VOLUMM
def test_volumm_le_seuil_et_le_montant_sont_les_MEMES_des_deux_cotes(volumm_case):
    """L'ACCORD sur les DEUX axes : le RANG du franchissement (`nrOfRepairs`-ieme reparation) et le
    MONTANT (`hpToHeal[3]`). Le rang est comptable parce que `EcogSupport` est retire (cf. l'en-tete)
    et que chaque tour ne porte donc QUE la reparation de Vynn."""
    r = volumm_case()
    nr, hp = _var(P.VOLUMM, "nrOfRepairs", LEVEL), _var(P.VOLUMM, "hpToHeal", LEVEL)
    assert nr > 0 and hp > 0
    assert r["mounted"]["abilityId"] == P.VOLUMM_ID and r["mounted"]["level"] == LEVEL
    assert r["native_repairs_seen"] >= nr, (
        "seulement %s reparation(s) emise(s) alors que le seuil est a %d : la mesure ne peut pas "
        "franchir le seuil (%s)" % (r["native_repairs_seen"], nr, r.get("native")))
    assert r["native_healed_cumul"] == nr, (
        "NATIF : soin a la %s-ieme reparation, attendu la %d-ieme -- %s"
        % (r["native_healed_cumul"], nr, r.get("native")))
    assert r["native_heal"]["vynn_delta"] == hp, (
        "NATIF : soin de %s PV, attendu hpToHeal[%d] = %d"
        % (r["native_heal"]["vynn_delta"], LEVEL, hp))
    assert r["port"]["healed_at"] == nr and r["port"]["hp_delta"] == hp, (
        "PORT : soin au rang %s pour %s PV, attendu (%d, %d)"
        % (r["port"]["healed_at"], r["port"]["hp_delta"], nr, hp))


def test_volumm_sans_le_rail_le_port_est_inerte(volumm_case):
    """CONTRE-EPREUVE 1 -- `VolummsMasterArtifice` n'est PAS dans le kit gameconfig de Vynn : sans
    le canal tertiaire, aucun trigger n'est inscrit et le compteur n'existe pas."""
    r = volumm_case()
    assert r["port"]["tertiary"] == P.VOLUMM
    assert r["port_no_rail"]["healed_at"] is None, (
        "sans le canal #357 le port ne doit RIEN soigner, or il soigne au rang %s"
        % (r["port_no_rail"]["healed_at"],))


def test_volumm_le_niveau_lu_est_le_TERTIAIRE_pas_celui_des_passifs(volumm_case):
    """CONTRE-EPREUVE 2 -- au niveau 3, `nrOfRepairs` vaut 8 ; le palier CLAMPE (niveau passif 50)
    en vaut 7. Le bras mute doit donc franchir le seuil UN CRAN TROP TOT."""
    r = volumm_case()
    nr, nr_clamped = _var(P.VOLUMM, "nrOfRepairs", LEVEL), _var(P.VOLUMM, "nrOfRepairs", 50)
    assert nr != nr_clamped, "le niveau %d ne separe RIEN -- changer de bras" % LEVEL
    assert r["port_passive_level"]["healed_at"] == nr_clamped, (
        "le bras mute devrait franchir au rang CLAMPE %d, il franchit a %s"
        % (nr_clamped, r["port_passive_level"]["healed_at"]))
    assert r["port_passive_level"]["healed_at"] != r["native_healed_cumul"], (
        "la contre-epreuve ne rougit pas : lire le niveau des PASSIFS donne le meme rang que le "
        "natif -- le montage ne separe pas les deux champs")
