"""#419-r1-tr14-r5-r1 / -r4 -- la TABLE de substitution d'attaque normale, et les DEUX TRAITS qui la
SUPPRIMENT. Un seul foyer natif, `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`.

CE QUE CE FICHIER GARDE -- six choses, aucune redondante :

  1. **LES 14 ENTREES DE LA TABLE**, une par une, contre le natif. La table du port transcrit le
     `Dictionary` statique ecrit par `StaticBattleRules.TriggeredAbility$$.cctor` ; ce test refuse
     de la croire sur parole et confronte chaque paire au seul canal qui publie le resultat de la
     fabrique -- `decisionView.units[].abilities` `kind == "normal"`, c.-a-d.
     `ActiveAbilityComponent.NormalAttackType@0x28`. Deux chemins independants : cinq porteurs
     `lineup` SANS montage, neuf par greffe ecrite de `BC.Units[].PassiveAbilities`.
  2. **LES CONTROLES APPARIES.** Trois unites sans passif substituant doivent rendre
     `69 Loki_NormalAttack`. Sans eux, un montage qui n'aurait RIEN installe rendrait des `69`
     partout et se lirait comme « aucune substitution » plutot que comme « montage mort ».
  3. **LA BOUCLE, PAS LA TABLE** -- `GetCustomNormalAttackTypeFromPassive` rend au PREMIER passif
     substituant. C'est ce que la table incomplete cassait : elle SAUTAIT l'entree absente et
     donnait la main a la suivante. Deux bras, meme paire de passifs, ordres INVERSES, deux
     reponses natives differentes.
  4. **LA CONTRE-EPREUVE MORD** -- rejouer la table telle qu'elle etait avant #419-r1-tr14-r5-r1
     (quatre entrees) DEPLACE la prediction du port sur le bras `[HeavyBoltPistol, Boltstorm]` : il
     folde `Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction` que le natif ne folde
     pas. Un vert de (3) sans ce cran ne prouverait pas que c'est la table qui le produit.
  5. **LA GARDE DES TRAITS, cote NATIF** -- `Traits.Contains(0x0e Erratic)` ou
     `Contains(0x15 Harmless)` -> `return` SEC : le natif ne publie AUCUNE ability `kind ==
     "normal"`. Bras APPARIE (memes unites, memes rosters, seuls les `BC.Units[].Traits` different)
     plus un temoin SANS trait dans CHAQUE bras.
  6. **LA GARDE DES TRAITS, cote PORT** -- `state_bridge.build_from_state(...).normal_ids` est VIDE
     pour ces unites et NON VIDE pour le temoin. C'est la voie OFFLINE, la seule des deux a DERIVER
     l'existence de l'attaque normale (la voie LIVE la lit dans `decisionView`, donc la mesure).

⚠ ZERO unite de ce build ne porte `Erratic` ni `Harmless` -- 683 kits gameconfig et les 175 unites
du seed BC balayes. Le montage ECRIT est donc le seul chemin de confrontation, et c'en est un : ce
n'est ni « non pertinent » ni « non confrontable ».

Mesures et RE : `docs/rl/case-419-r1-tr14-r5-dispatch-attaque-normale.md` §10-§12. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr14r5_r1r4_normal_attack_table.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5_r1r4_normal_attack_table as P
from engine.services.custom_normal_attack import CUSTOM_NORMAL_ATTACK_BY_PASSIVE

NATIVE_TABLE_SIZE = 14      # les 14 `Add` du `.cctor` -- cf. la case-doc


@pytest.fixture(scope="module")
def table_rows(rpc, tmp_path_factory, build_runner):
    """Les 14 entrees + 3 controles, sur DEUX runners (porteurs naturels / greffes)."""
    P.os.environ["A35_LOGS"] = str(tmp_path_factory.mktemp("tr14r5_r1_table"))
    try:
        return P.run_table(rpc, lambda seed, extra: build_runner(seed, extra)["rid"],
                           verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def order_measure(live_session, rpc, tmp_path_factory, build_runner):
    """Les deux ORDRES de la meme paire de passifs + la prediction du port, table livree contre
    table d'avant."""
    P.os.environ["A35_LOGS"] = str(tmp_path_factory.mktemp("tr14r5_r1_order"))
    try:
        return P.run_order(live_session, rpc,
                           lambda seed, extra: build_runner(seed, extra)["rid"], verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def trait_rows(rpc, tmp_path_factory, build_runner):
    """Bras APPARIE `ctrl` / `trait` : seuls les `BC.Units[].Traits` des deux unites different."""
    P.os.environ["A35_LOGS"] = str(tmp_path_factory.mktemp("tr14r5_r4_traits"))
    try:
        return P.run_traits(rpc, lambda seed, extra: build_runner(seed, extra)["rid"],
                            verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_table_a_la_taille_du_dictionnaire_natif():
    """(0) La table PORTEE compte exactement les 14 entrees du `.cctor`. Cran OFFLINE : il rougit
    si un futur commit en retire une sans repasser par la mesure."""
    assert len(CUSTOM_NORMAL_ATTACK_BY_PASSIVE) == NATIVE_TABLE_SIZE, (
        f"{len(CUSTOM_NORMAL_ATTACK_BY_PASSIVE)} entrees portees contre {NATIVE_TABLE_SIZE} `Add` "
        f"dans `StaticBattleRules.TriggeredAbility$$.cctor` -- une table PARTIELLE ne fait pas "
        f"'moins de dispatch', elle en fait un FAUX (l'entree manquante est sautee par la boucle "
        f"'premier passif gagnant' et la main passe a la suivante)")


def test_les_quatorze_entrees_sont_conformes_au_natif(table_rows):
    """(1) Chaque paire {passif -> attaque normale} de la table est celle que la FABRIQUE pose."""
    entries = [r for r in table_rows if r["arm"] in ("natural", "graft")]
    assert len(entries) == NATIVE_TABLE_SIZE, (
        f"{len(entries)} entrees mesurees au lieu de {NATIVE_TABLE_SIZE} -- le montage n'exerce "
        f"pas toute la table")
    bad = [f"{r['unit']}/{r['passive']}: natif {r['native']} != {r['expected']}"
           for r in entries if not r["ok"]]
    assert not bad, (
        "la table portee diverge du dictionnaire natif : " + " | ".join(bad) +
        " -- ces valeurs se LISENT au `.cctor` et se CONFRONTENT ici, elles ne se deduisent "
        "d'aucun nom (`HeavyBoltPistol` rend `TemplarInitiateNormalAttack`, et "
        "`RogalDorn_NormalAttack` n'est la valeur d'AUCUNE cle passive)")


def test_les_controles_rendent_l_attaque_generique(table_rows):
    """(2) Sans passif substituant, le natif rend `69 Loki_NormalAttack`. C'est ce qui distingue
    « aucune substitution » de « montage mort »."""
    ctrls = [r for r in table_rows if r["arm"].endswith("ctrl")]
    assert len(ctrls) >= 3, f"{len(ctrls)} controles au lieu de 3 attendus"
    bad = [f"{r['unit']}: {r['native']}" for r in ctrls if not r["ok"]]
    assert not bad, (
        "des unites SANS passif substituant portent une attaque normale CUSTOM : " +
        " | ".join(bad) + " -- le discriminant du montage est casse, tout vert de ce fichier "
        "serait vide")


def test_le_premier_passif_substituant_gagne(order_measure):
    """(3) MEME paire de passifs, ordres INVERSES, reponses natives DIFFERENTES."""
    rows = {r["arm"]: r for r in order_measure["rows"]}
    first, recip = rows["order-first"], rows["order-recip"]
    assert first["ok"], (
        f"`[{P.ORDER_FIRST}, {P.ORDER_SECOND}]` : le natif rend {first['native']} au lieu de "
        f"{first['expected']} -- `GetCustomNormalAttackTypeFromPassive` rend au PREMIER passif "
        f"substituant, pas au premier que la table du port connait")
    assert recip["ok"], (
        f"`[{P.ORDER_SECOND}, {P.ORDER_FIRST}]` (bras RECIPROQUE) : le natif rend "
        f"{recip['native']} au lieu de {recip['expected']}")
    assert first["native"] != recip["native"], (
        f"les deux ordres rendent la MEME attaque normale ({first['native']}) -- le montage ne "
        f"discrimine plus l'ordre, et le vert ci-dessus ne prouve rien")


def test_la_prediction_du_port_suit_le_premier_passif(order_measure):
    """(3bis) Sur le bras `[HeavyBoltPistol, Boltstorm]`, le port accorde avec le natif -- donc il
    ne folde PAS `Boltstorm`, que la fabrique n'a pas retenu."""
    pred = order_measure["pred"]
    nat, port = pred["nat"], pred["port"]
    assert (port["dmin"], port["dmax"]) == (nat["dmin"], nat["dmax"]), (
        f"tuile {pred['tile']}, ability native {pred['ab']} : bornes portees "
        f"({port['dmin']},{port['dmax']}) contre natif ({nat['dmin']},{nat['dmax']})")
    assert port["hits"] == nat["hits"], (
        f"{port['hits']} coups portes contre {nat['hits']} natifs -- un fold de trop ?")


def test_contre_epreuve_table_d_avant_mord(order_measure):
    """(4) La table d'AVANT #419-r1-tr14-r5-r1 (quatre entrees) DEPLACE la prediction du port. Si
    elle est inerte, ce n'est plus la table qui produit le vert de (3bis)."""
    pred = order_measure["pred"]
    nat, before = pred["nat"], pred["before"]
    assert (before["dmin"], before["dmax"]) != (nat["dmin"], nat["dmax"]), (
        f"table d'avant : le port rend toujours ({before['dmin']},{before['dmax']}) == natif -- la "
        f"contre-epreuve est INERTE. Elle devrait faire sauter `{P.ORDER_FIRST}` dans la boucle et "
        f"folder `{P.ORDER_SECOND}` a tort")


def test_les_traits_suppriment_l_attaque_normale_cote_natif(trait_rows):
    """(5) Bras `trait` : AUCUNE ability `kind == 'normal'`. Bras `ctrl` : une. Temoins : une."""
    for r in trait_rows:
        has = r["native"] is not None
        assert has == r["expect_native"], (
            f"bras {r['arm']}, {r['unit']} (trait {r['trait']}) : le natif "
            f"{'publie ' + str(r['native']) if has else 'ne publie AUCUNE attaque normale'} "
            f"alors qu'on attend {'une attaque normale' if r['expect_native'] else 'AUCUNE'} -- "
            f"`AddNormalAttackAbility` rend SEC sur `Traits.Contains(0x0e|0x15)`")


def test_le_port_offline_suit_la_garde_des_traits(trait_rows):
    """(6) `state_bridge.build_from_state(...).normal_ids` : VIDE sous le trait, NON VIDE sans."""
    measured = [r for r in trait_rows if r["port_normal_ids"] is not None]
    assert measured, "aucune mesure du port -- le montage n'a rien exerce"
    for r in measured:
        if r["arm"] == "trait":
            assert r["port_normal_ids"] == [], (
                f"{r['unit']} porte `{r['trait']}` et le port lui laisse "
                f"normal_ids={r['port_normal_ids']} -- il generera, scorera et pourra CHOISIR une "
                f"attaque normale que le natif ne propose pas (degradation PERMISSIVE)")
        else:
            assert r["port_normal_ids"], (
                f"bras `ctrl`, {r['unit']} sans le trait : normal_ids VIDE -- la garde deborde sur "
                f"des unites qui ont bel et bien une attaque normale")


def test_contre_epreuve_garde_des_traits_mord(trait_rows):
    """(6bis) Garde COUPEE (`has_normal_attack` -> True), c.-a-d. le port d'AVANT
    #419-r1-tr14-r5-r4 : sur le bras `trait` il REDONNE une attaque normale. Si la mutation est
    inerte, le vide de (6) vient d'autre chose que la garde -- unite sans arme, montage mort -- et
    le fichier serait un vert creux."""
    trait = [r for r in trait_rows if r["arm"] == "trait" and r["port_ungated"] is not None]
    assert trait, "aucune mesure du bras `trait` -- le montage n'a rien exerce"
    for r in trait:
        assert r["port_ungated"], (
            f"{r['unit']} porte `{r['trait']}` : garde COUPEE, le port rend toujours "
            f"normal_ids={r['port_ungated']} (vide) -- la contre-epreuve est INERTE, ce n'est donc "
            f"pas la garde qui produit le vide mesure par (6)")
        assert r["port_ungated"] != r["port_normal_ids"], (
            f"{r['unit']} : garde armee et garde coupee rendent la MEME chose "
            f"({r['port_normal_ids']}) -- la garde ne mord pas")
    # RECIPROQUE : sur le bras `ctrl`, couper la garde ne doit RIEN changer (aucun trait
    # suppresseur). Un fix qui deborderait sur des unites ordinaires le ferait rougir.
    for r in (x for x in trait_rows if x["arm"] == "ctrl" and x["port_ungated"] is not None):
        assert r["port_ungated"] == r["port_normal_ids"], (
            f"bras `ctrl`, {r['unit']} : couper la garde change normal_ids "
            f"({r['port_normal_ids']} -> {r['port_ungated']}) alors qu'aucun trait suppresseur "
            f"n'est pose -- la garde mord la ou elle ne devrait pas")
