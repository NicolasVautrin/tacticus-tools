"""GARDE LIVE #1013 -- `ParagonSpear` (relique 1494 de `custoKyrus`), DEUX faces.

CE QUE CES GARDES EXIGENT, ET DE QUEL ARTEFACT NATIF

  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ParagonSpearAbility$$CreateTrigger` /
    `$$CreateBehaviour` / `$$GetPossibleTargets` -> l'arbre DSL de
    `engine/runner/operations/triggers/loki/paragon_spear.py`, inscrit dans
    `RELIC_ABILITY_TRIGGERS` ;
  * `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage`, branche
    `HasTriggeredAbility(0x5d6 = 1494)` -- le natif NOMME cette ability -> `weaver_of_fate.
    is_attack_max_out_damage_on_crit`, transmis aux trois vecteurs d'attaque par
    `damage_hits._run_hits(max_out_on_crit=...)`.

POURQUOI LE NIVEAU 1, ET PAS 50. `AbilityConfiguration$$TryGetVariableArrayForLevel` CLAMPE au
dernier palier : un port qui lirait le niveau des PASSIFS (50 dans tout runner normalise) rendrait
`minDmg[10]/maxDmg[10]`. Au niveau 1 les deux intervalles sont **DISJOINTS** (`[2155, 2940]` contre
`[3202, 4368]` au build courant) -- c'est le seul regime ou les deux hypotheses se separent, et le
test le VERIFIE avant de conclure. A 50 elles rendraient le meme nombre et le lot ne conclurait rien.

POURQUOI DEUX REGIMES DE CRIT. `CritChance = 0` valide l'arbre DSL, les bornes, les coups, le profil
et le niveau tertiaire ; `CritChance = 100` valide la branche max-out, et ELLE SEULE (en crit 0 le
port etait deja bit-exact AVANT #1013). Un seul des deux ne separerait pas les deux faces.

Montage : `probe_1013_paragon_spear.py` (voie `--dist`/`--level`/`--crit`) et
`probe_1013_temoin_crit.py` (le TEMOIN `MartialApotheosis`, meme vecteur turn-start, port valide de
longue date -- il garde la NON-REGRESSION du foyer partage que #1013 touche). ASCII only.

"""
from __future__ import annotations

import pytest

import probe_1013_paragon_spear as PS
import probe_1013_temoin_crit as TC
from engine.runner.operations.triggers.loki import paragon_spear as PSA

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Les DEUX faces portees, et les deux probes de montage.
        "scripts/python/engine/runner/operations/triggers/loki/paragon_spear.py",
        "scripts/python/engine/runner/operations/triggers/loki/weaver_of_fate.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/probe_1013_paragon_spear.py",
        "scripts/python/probe_1013_temoin_crit.py",
        # Le PIPELINE DE DEGAT PARTAGE : la branche max-out y vit (`_run_hits`), et les trois
        # vecteurs d'attaque la transmettent.
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/damage_hits.py",
        "scripts/python/engine/runner/operations/damage_ops/*.py",
        # Le rail de relique #357 (niveau/multiplicateur TERTIAIRES) et les selecteurs de l'arbre.
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/abilities/base.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/entities/selectors/*.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Ce fichier confronte au LIVE deux faces d'un MEME artefact natif : l'arbre DSL de "
              "`ParagonSpearAbility` et la branche `HasTriggeredAbility(1494)` d'"
              "`IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage`. La seconde ne vit PAS "
              "dans le module de l'ability mais dans le pipeline de degat PARTAGE (`damage_hits."
              "_run_hits`, transmis par les trois vecteurs d'attaque) : son rayon deborde donc "
              "tout perimetre enumerable -- canal crit, bornes, bouclier, armure, rail de relique "
              "et harnais de runner peuvent tous en changer le verdict. `toujours: True` est ici "
              "un RESULTAT mesure, pas un aveu : la liste ci-dessus dit ou LIRE, elle ne "
              "pretend pas borner. Un declencheur etroit sur un test qui compare BIT A BIT un "
              "degat serait un faux vert.",
}


def _bounds(level: int) -> tuple:
    from engine.entities.effects.magnitude import ability_var
    return (int(ability_var(PS.RELIC, "minDmg", level, multiplier_pct=100) or 0),
            int(ability_var(PS.RELIC, "maxDmg", level, multiplier_pct=100) or 0))


@pytest.fixture(scope="module")
def spear_case(build_runner, rpc):
    """Fabrique NOMMEE et REJOUABLE : `spear_case(dist=1, level=1, crit=None)` -> le releve.

    `custoKyrus` (DANS le pool rank 17 -> etat 2 de la gate relique, aucune injection) equipe de
    `ParagonSpear` au niveau EXACT demande, cote ADVERSAIRE pour que le build demarre au tour du
    JOUEUR ; on DRIVE une victime a la distance hex voulue et les autres HORS de portee, puis
    `endturn` fait ENTRER dans son turn-start. La MEME capture pre-`endturn` est rejouee TROIS fois
    cote port -- canal #357 fourni / non fourni / fourni mais niveau lu sur le PASSIF."""
    made, cache = [], {}

    def make(dist: int = 1, level: int = 1, crit=None):
        key = (dist, level, crit)
        if key in cache:                   # un montage = un BUILD ; les tests le repartagent
            return cache[key]

        def build(seed, extra=None):
            r = build_runner(seed, extra=list(extra or []))
            made.append(r["rid"])
            return r
        base = PS.build_args
        if crit is not None:
            PS.build_args = (lambda lvl, _b=base, _c=crit:
                             _b(lvl) + ["--unit-stat", "%s:CritChance=%d" % (PS.CARRIER, _c)])
        try:
            cache[key] = PS.run_any(rpc, dist=dist, level=level, build_runner=build, keep=True)
            return cache[key]
        finally:
            PS.build_args = base

    yield make
    for rid in made:                       # dispose MES runners, jamais ceux des autres
        try:
            rpc("disposeRunner", {"runnerId": rid}, 40)
        except Exception:                  # pragma: no cover - teardown best-effort
            pass


def _ok(r):
    assert r.get("ok"), "montage NON obtenu : %s" % (r.get("why"),)
    return r


# --- FACE 1 : l'arbre DSL (regime NON critique, celui qui valide le ciblage et les bornes) --------

@pytest.mark.parametrize("dist,branche", [(1, "adjacent"), (2, "ranged")])
def test_les_deux_branches_de_GetPossibleTargets_frappent_et_le_degat_est_bit_exact(
        spear_case, dist, branche):
    """`If(AmountIsGreaterThanZero(adjacents), adjacents, distants)` -- les DEUX branches, en
    `CritChance = 0` (le regime qui isole l'arbre du max-out).

    d=1 prend la branche ADJACENTE, d=2 la branche DISTANTE (`range` = 2). Le degat doit egaler le
    natif BIT pour BIT : le flux RNG est prouve aligne par le meme releve (`mti` et tableau MT
    final identiques), donc un ecart ne pourrait etre qu'une erreur d'arithmetique."""
    r = _ok(spear_case(dist=dist, level=1, crit=0))
    assert r["pool"]["branch"] == branche, (
        "a d=%d le port prend la branche %r, attendu %r (pool=%s)"
        % (dist, r["pool"]["branch"], branche, r["pool"]))
    assert r["port"]["events"] == 1, (
        "le trigger n'a pas fire une fois et une seule : %s" % (r["port"],))
    assert r["native_delta"] > 0, "le NATIF n'a rien inflige -- la mesure ne porte sur rien"
    assert r["rng"]["mti_after_port"] == r["rng"]["mti_after_native"], (
        "flux RNG DESALIGNE (port %s tirages, natif %s) -- tout ecart de degat serait un artefact"
        % (r["rng"]["mti_after_port"], r["rng"]["mti_after_native"]))
    assert r["rng"]["mt_final_equal"], (
        "les tableaux MT finaux different : le port et le natif n'ont pas consomme les MEMES tirages")
    assert r["port"]["delta"] == r["native_delta"], (
        "d=%d (%s) : port %s vs natif %s" % (dist, branche, r["port"]["delta"], r["native_delta"]))


def test_une_seule_cible_est_frappee_et_c_est_celle_du_pool(spear_case):
    """`First(SortByDistance(Randomize(...)), 1)` -- UNE cible, et c'est un element du pool.

    Deux ennemis sont montes ; un `First(1)` manquant en frapperait deux."""
    r = _ok(spear_case(dist=1, level=1, crit=0))
    assert len(r["native_hit"]) == 1, (
        "le NATIF a touche %s unites, attendu 1 (`First(1)`)" % (r["native_hit"],))
    assert r["port"]["hit_units"] == r["native_hit"], (
        "le port frappe %s, le natif %s" % (r["port"]["hit_units"], r["native_hit"]))
    assert r["port"]["target"] in r["pool"]["pool"], (
        "la cible %s n'est pas dans le pool %s" % (r["port"]["target"], r["pool"]["pool"]))


def test_hors_de_portee_le_trigger_ne_fire_PAS_des_deux_cotes(spear_case):
    """CONTRE-EPREUVE GEOMETRIQUE -- `AmountIsGreaterThanZero(GetPossibleTargets())`.

    A d=3 (au-dela de `range` = 2) le pool est VIDE : le natif n'inflige RIEN et le port non plus.
    Sans ce bras, un port qui frapperait n'importe qui passerait les tests ci-dessus."""
    r = _ok(spear_case(dist=3, level=1, crit=0))
    assert r["pool"]["branch"] == "vide", "le pool devrait etre VIDE a d=3 : %s" % (r["pool"],)
    assert r["native_delta"] == 0, "le NATIF a inflige %s a d=3 -- hors portee" % r["native_delta"]
    assert r["port"]["events"] == 0 and r["port"]["delta"] == 0, (
        "le port a fire hors de portee : %s" % (r["port"],))


# --- FACE 2 : la branche max-out du natif, celle qui NOMME cette ability -------------------------

def test_un_coup_CRITIQUE_est_maxe_et_le_port_le_suit(spear_case):
    """`IsAttackMaxOutDamage` branche `HasTriggeredAbility(1494)` : sur un coup CRITIQUE, la valeur
    est portee au MAX avant le bonus de crit -- donc DETERMINISTE, independante du tirage.

    C'est ce determinisme qui prouve la branche : en `CritChance = 100` le natif rend
    `2 x (maxDmg[level] + CritDamage)` quelle que soit la seed, alors qu'en `CritChance = 0` il
    VARIE. Le test assertionne les deux."""
    r1 = _ok(spear_case(dist=1, level=1, crit=100))
    assert r1["rng"]["mt_final_equal"], "flux RNG desaligne -- la comparaison ne porte sur rien"
    assert r1["port"]["delta"] == r1["native_delta"], (
        "coup critique : port %s vs natif %s -- la branche max-out n'est pas suivie"
        % (r1["port"]["delta"], r1["native_delta"]))
    # le crit DOIT avoir eu lieu, sinon ce test mesure le regime non-critique
    crits = ((r1["port"].get("raw") or {}).get("attack") or {}).get("crits") or []
    assert crits and all(crits), "aucun coup n'a crite (%s) -- `CritChance = 100` n'a pas mordu" % (crits,)


def test_le_max_out_ne_deborde_PAS_sur_les_coups_NON_critiques(spear_case):
    """CONTRE-EPREUVE DE PORTEE -- l'autre facon de se tromper.

    Le natif gate la branche sur `isCritical` : un port qui degenererait les bornes en amont
    (comme le fait `_apply_max_out` pour l'effet 1185) maxerait AUSSI les coups non critiques. Le
    releve `CritChance = 0` doit donc rester VARIABLE d'une seed a l'autre et coller au natif."""
    a = _ok(spear_case(dist=1, level=1, crit=0))
    ph = ((a["port"].get("raw") or {}).get("attack") or {}).get("per_hit") or []
    assert len(ph) >= 2, "il faut au moins 2 coups pour voir une variabilite : %s" % (ph,)
    assert len(set(ph)) > 1, (
        "les %d coups NON critiques valent tous %s -- le max-out deborde hors du crit" % (len(ph), ph[0]))
    assert a["port"]["delta"] == a["native_delta"]


def test_le_temoin_MartialApotheosis_reste_bit_exact_dans_les_DEUX_regimes(rpc):
    """NON-REGRESSION du foyer PARTAGE que #1013 touche (`damage_hits._run_hits`).

    `MartialApotheosis` emprunte le MEME vecteur turn-start et la MEME feuille
    `AttackWithAttackDamage`, mais son porteur ne porte PAS `ParagonSpear` : le flag doit rester
    FAUX pour lui, dans les deux regimes de crit. C'est le bras qui montre que la branche neuve
    n'est pas devenue inconditionnelle."""
    for crit in (0, 100):
        r = TC.mesure(rpc, "MartialApotheosis", crit)
        assert r.get("ok"), "temoin NON MESURE (crit=%d) : %s" % (crit, r.get("why"))
        assert r["native_delta"] > 0, "le temoin n'a rien inflige (crit=%d)" % crit
        assert r["port_delta"] == r["native_delta"], (
            "TEMOIN crit=%d : port %s vs natif %s -- #1013 a debord'e sur un porteur qui ne "
            "porte PAS la lance" % (crit, r["port_delta"], r["native_delta"]))


# --- Le RAIL de la relique, et le NIVEAU ---------------------------------------------------------

def test_la_relique_est_montee_et_le_port_l_inscrit(spear_case):
    """Etage 0 : hierarchie **3** (`AddConfiguredAbilities` -> `TryAdd(id, tertiaryState, 3)`) cote
    natif, et `ParagonSpearAbility` inscrite cote port (5e chemin de registration, #357)."""
    r = _ok(spear_case(dist=1, level=1, crit=0))
    assert r["mounted"]["abilityId"] == PS.RELIC_ID and r["mounted"]["level"] == 1, (
        "l'entree de hierarchie 3 lue n'est pas celle attendue : %s" % (r["mounted"],))
    assert "ParagonSpearAbility" in r["port"]["inscribed"], (
        "le port n'inscrit pas la relique : %s" % (r["port"]["inscribed"],))
    assert r["port"]["tertiary"] == PS.RELIC and r["port"]["level"] == 1, (
        "le canal #357 ne seede pas le couple tertiaire : %s" % (r["port"],))


def test_sans_le_rail_357_le_port_est_INERTE(spear_case):
    """CONTRE-EPREUVE 1 -- l'etat d'AVANT #357, rejoue sur LA MEME capture.

    `load_state(ability_states=False)` : le rail ne voit pas l'item EQUIPE, donc AUCUN trigger
    n'est inscrit. `False` et pas `None` : depuis #363 `None` veut dire AUTO et le bras
    re-tirerait le payload lui-meme, ce qui en ferait un vert qui ment."""
    r = _ok(spear_case(dist=1, level=1, crit=0))
    assert r["port_no_rail"]["events"] == 0 and r["port_no_rail"]["delta"] == 0, (
        "sans le canal #357 le port ne doit RIEN infliger, or il rend %s" % (r["port_no_rail"],))
    assert r["native_delta"] > 0, "le natif, lui, frappe -- c'est bien un ECART que #357 ferme"


@pytest.mark.parametrize("level", [1])
def test_le_niveau_lu_est_le_TERTIAIRE_pas_celui_des_passifs(spear_case, level):
    """CONTRE-EPREUVE 2 -- l'axe MAGNITUDE, au niveau BAS exige par le montage.

    Le bras mute (`triggered_ability_state` force sur le couple PASSIF) lit le palier CLAMPE. Le
    test ASSERTIONNE d'abord que les deux intervalles sont DISJOINTS a ce niveau : sinon les deux
    hypotheses pourraient rendre le meme nombre et le bras ne separerait RIEN."""
    lo, hi = _bounds(level)
    lo_c, hi_c = _bounds(50)
    assert hi < lo_c, (
        "niveau %d : [%d, %d] et le palier clampe [%d, %d] se CHEVAUCHENT -- ce niveau ne separe "
        "pas les deux hypotheses, changer de bras" % (level, lo, hi, lo_c, hi_c))
    r = _ok(spear_case(dist=1, level=level, crit=0))
    assert r["port"]["level"] == level, (
        "`tertiary_ability_level` = %s, attendu %d" % (r["port"]["level"], level))
    assert r["port"]["delta"] == r["native_delta"], (
        "niveau %d : port %s vs natif %s" % (level, r["port"]["delta"], r["native_delta"]))
    assert r["port_passive_level"]["delta"] != r["native_delta"], (
        "la contre-epreuve ne rougit PAS : lire le niveau des PASSIFS rend le meme resultat que le "
        "natif au niveau %d -- le montage ne separe pas les deux champs" % level)


def test_les_constantes_lues_sont_celles_du_gameconfig(spear_case):
    """`GetNumberConstant(0x16 = range)` et `GetDamageProfile()` -- lus, jamais codes en dur."""
    r = _ok(spear_case(dist=1, level=1, crit=0))
    assert r["port"]["range"] == PSA.paragon_spear_range() == r["pool"]["range"], (
        "le rayon differe entre le releve et la config : %s" % (r["port"],))
    assert r["port"]["profile"] == PSA.paragon_spear_damage_profile(), (
        "le profil differe : %s" % (r["port"],))
