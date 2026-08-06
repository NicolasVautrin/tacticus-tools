"""#419-r1-tr14-r3 -- GARDE : le spread +/-20 % DISCRIMINE des que la cible peut MOURIR.

Ce que ce fichier verrouille, et pourquoi chaque point existe :

 1. **LE TEMOIN EST NON NUL** -- a spread 20 les bornes RAW sont DISTINCTES, et la mutation
    `spread0` les REDUIT A UN POINT. Sans ce cran, une inertie observee ne prouverait rien : c'est
    exactement le regime degenere qui avait fait ecrire « spread non discrimine » a la tranche 14.
 2. **LES TROIS REGIMES SONT INSTALLES** -- `hp_hors` (aucun palier), `fenetre_kill` (`kill` sans
    `killSure`), `fenetre_overkill` (`MightBeOverkill` sans `WillBeOverkill`, kill acquis des DEUX
    cotes donc l'overkill est ISOLE). Les PV de chaque cran sont DERIVES des bornes mesurees, pas
    ecrits en dur : si le montage bouge, le cran suit ou la garde rougit.
 3. **LE NATIF ARBITRE** -- a chaque cran, le terme porte au spread par DEFAUT egale le terme natif
    (bras apparie). C'est ce qui fait du natif le juge, et non le port.
 4. **LA CONTRE-EPREUVE MORD, ET SON INERTIE EST EXIGEE** -- `spread0` doit MORDRE aux deux fenetres
    et rester INERTE au temoin. `a_mordu` est SEPARE du verdict ; l'inertie est assertionnee A
    L'ENVERS plutot que tue.
 5. **LA MUTATION S'ECARTE DU NATIF** -- aux deux fenetres, `spread_pct=0` produit un terme
    DIFFERENT du natif. C'est le point qui tranche `#419-r1-tr5-r2` : les deux lectures ne peuvent
    pas etre vraies ensemble, et c'est celle a spread 0 qui est fausse.

(!) CE QUE CE TEST N'ASSERTE PAS : la conformite en NIVEAU (`natif == port` sur la paire ENTIERE).
La paire porte un ecart hors-perimetre issu du composite de l'ATTAQUE NORMALE, chiffre dans
`docs/rl/case-419-r1-tr14-heavy-bolt-pistol-playbook.md`. Seul le TERME (difference des bras) est
asserte -- l'asserter en niveau ferait rougir cette garde pour une cause etrangere.

Montage : celui de la tranche 14 (greffe de 1083 sur `tauMarksman`, bras apparie, board `MC1_67`),
avec pour seul degre de liberte ajoute les PV de la cible. TROIS couples de runners, un par cran.
ASCII only. Probe jumeau : `scripts/python/probe_419r1tr14r3_spread_paliers_kill.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r3_spread_paliers_kill as P

EPS = P.EPS


@pytest.fixture(scope="module")
def spread_rows(live_session, rpc, build_runner, tmp_path_factory):
    """Les trois crans. Le PREMIER (`hp_hors`) est AUSSI le calibrage : il fournit les bornes RAW
    dont les deux autres DERIVENT leurs PV. Un `MontageError` devient un ECHEC, jamais un skip."""
    logs = str(tmp_path_factory.mktemp("hbp_tr14r3"))
    rows = []

    def _un_cran(cran, hp, layout):
        """Un cran = DEUX runners appariés, mesures, puis DISPOSES TOUT DE SUITE.

        La liberation au fil de l'eau n'est pas cosmetique : sans elle les SIX runners des trois
        crans vivraient jusqu'a la fin du module et satureraient le budget PARTAGE. Le teardown de
        la conftest les re-dispose sans broncher (il avale l'exception « deja parti »)."""
        g = build_runner(P.SEED, P.build_args(logs, "graft", hp))["rid"]
        b = build_runner(P.SEED, P.build_args(logs, "base", hp))["rid"]
        try:
            return P.mesure_sur_runners(live_session, rpc, g, b, cran, hp, layout)
        finally:
            P._dispose(rpc, g)
            P._dispose(rpc, b)

    try:
        r0 = _un_cran("hp_hors", P.HP_HORS, None)
        rows.append(r0)
        layout = r0["layout"]
        # Les PV des crans derivent des bornes ATTENDUES (centre mesure + spread LU DE LA BATAILLE),
        # jamais des bornes que le playbook rend : sinon un port mute ferait echouer le CALIBRAGE, et
        # la garde accuserait le montage pour une faute du port. Mesure a l'appui : ce chemin-la
        # rendait « le montage NE PEUT PAS discriminer ». Cf. `P.bornes_attendues`.
        raw_min, raw_max = P.bornes_attendues(int(r0["spread20"]["rawHealthDmgMin"]),
                                              int(r0["spread20"]["rawHealthDmgMax"]))
        if raw_max - raw_min < 2:
            pytest.fail(f"amplitude ATTENDUE du spread trop faible ({raw_max - raw_min}) : elle "
                        f"vient de `BattleConfiguration.Damage.DamageSpreadPercentage`, donc c'est "
                        f"bien le MONTAGE (ou la BC) qui ne peut pas discriminer -- pas le port",
                        pytrace=False)
        for cran in ("fenetre_kill", "fenetre_overkill"):
            hp = P.hp_du_cran(cran, raw_min, raw_max)
            rows.append(_un_cran(cran, hp, layout))
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)
    return rows


def test_spread_temoin_est_non_nul(spread_rows):
    """(1) TEMOIN NON NUL : a spread 20 les bornes RAW sont DISTINCTES, et `spread0` les reduit a un
    POINT. Une inertie mesuree sans ce temoin ne prouve rien -- c'est le vice de la tranche mere."""
    for r in spread_rows:
        a, b = r["spread20"], r["spread0"]
        att = P.bornes_attendues(a["rawHealthDmgMin"], a["rawHealthDmgMax"])
        assert a["rawHealthDmgMin"] < a["rawHealthDmgMax"], (
            f"[{r['cran']}] TEMOIN NUL : le PORT rend des bornes RAW egales "
            f"({a['rawHealthDmgMin']}) la ou le spread LU DE LA BATAILLE "
            f"(`DamageSpreadPercentage`) en exige {list(att)} -- c'est la LECTURE du port qui est "
            f"en cause, pas le montage")
        assert b["rawHealthDmgMin"] == b["rawHealthDmgMax"], (
            f"[{r['cran']}] la mutation `spread0` n'a PAS mordu sur les bornes : "
            f"[{b['rawHealthDmgMin']}, {b['rawHealthDmgMax']}] au lieu d'un point")


def test_les_trois_regimes_sont_installes(spread_rows):
    """(2) ANTI-REGIME-DEGENERE : chaque cran installe REELLEMENT le palier qu'il annonce."""
    assert [r["cran"] for r in spread_rows] == list(P.CRANS), (
        f"les trois crans ne sont pas tous installes : {[r['cran'] for r in spread_rows]}")
    bad = [m for r in spread_rows for m in P.attester_regime(r)]
    assert not bad, "regimes NON installes :\n  " + "\n  ".join(bad)


def test_port_au_spread_defaut_reproduit_le_natif(spread_rows):
    """(3) LE NATIF ARBITRE : le terme porte au spread par DEFAUT egale le terme natif, cran par
    cran -- y compris dans les deux regimes ou les paliers kill/overkill sont franchis."""
    for r in spread_rows:
        e = r["port_term_20"] - r["native_term"]
        assert abs(e) <= EPS, (
            f"[{r['cran']}] TERME porte {r['port_term_20']:+.6f} != TERME natif "
            f"{r['native_term']:+.6f} (ecart {e:+.6f}) -- PV cible {r['hp_cible']}, "
            f"bornes RAW [{r['spread20']['rawHealthDmgMin']}, "
            f"{r['spread20']['rawHealthDmgMax']}]")


def test_contre_epreuve_spread0_mord_et_son_inertie_est_exigee(spread_rows):
    """(4) `a_mordu` SEPARE du verdict : `spread0` MORD aux deux fenetres, et reste INERTE au temoin
    -- l'inertie est EXIGEE, pas tue (c'est ce qui a manque a la tranche mere)."""
    dis = []
    for r in spread_rows:
        mordu = abs(r["deplacement_spread0"]) > EPS
        veut = P.attendu_mord(r["cran"])
        if mordu != veut:
            dis.append(f"[{r['cran']}] a_mordu={mordu} (attendu {veut}), "
                       f"deplacement={r['deplacement_spread0']:+.6f}")
    assert not dis, "contre-epreuve `spread0` en desaccord :\n  " + "\n  ".join(dis)


def test_spread0_s_ecarte_du_natif_dans_les_fenetres(spread_rows):
    """(5) CE QUI TRANCHE `#419-r1-tr5-r2` : dans les deux regimes a palier, `spread_pct=0` rend un
    terme DIFFERENT du natif. Les deux lectures du meme appel natif ne peuvent donc pas etre vraies
    ensemble -- et c'est celle a spread 0 qui est refutee."""
    ecarts = {}
    for r in spread_rows:
        if not P.attendu_mord(r["cran"]):
            continue
        e = r["port_term_00"] - r["native_term"]
        ecarts[r["cran"]] = e
        assert abs(e) > EPS, (
            f"[{r['cran']}] `spread_pct=0` reproduit AUSSI le natif (ecart {e:+.6f}) -- ce cran ne "
            f"discrimine donc pas les deux lectures, le montage a change de regime")
    assert ecarts, ("aucun cran a palier n'a ete mesure -- le test ne tranche RIEN "
                    "(un ensemble vide passerait pour vert)")


def test_les_feuilles_expliquent_le_deplacement(spread_rows):
    """(4bis) DECOMPOSITION PAR ETAGE, pas un scalaire : le deplacement de `spread0` est la SOMME
    des deplacements des trois feuilles du composite. Un ecart ici dirait que le terme bouge par un
    canal que la RE n'a pas nomme."""
    for r in spread_rows:
        a, b = r["spread20"], r["spread0"]
        somme = ((b["u_damage"] - a["u_damage"]) + (b["u_kill"] - a["u_kill"])
                 + (b["u_overkill"] - a["u_overkill"]))
        assert abs(somme - r["deplacement_spread0"]) <= EPS, (
            f"[{r['cran']}] le deplacement {r['deplacement_spread0']:+.6f} n'est PAS la somme des "
            f"feuilles ({somme:+.6f}) : dmg {a['u_damage']:.6f}->{b['u_damage']:.6f}, "
            f"kill {a['u_kill']:.6f}->{b['u_kill']:.6f}, "
            f"over {a['u_overkill']:.6f}->{b['u_overkill']:.6f}")


def test_le_cran_overkill_isole_bien_l_overkill(spread_rows):
    """(2bis) Le cran `fenetre_overkill` doit deplacer le terme par la SEULE feuille Overkill : le
    kill y est acquis des deux cotes, et le degat santé y est cape aux PV des deux cotes. Sans cette
    isolation, on ne saurait pas QUELLE feuille a bouge."""
    r = next((x for x in spread_rows if x["cran"] == "fenetre_overkill"), None)
    assert r is not None, "le cran `fenetre_overkill` n'a pas ete mesure"
    a, b = r["spread20"], r["spread0"]
    assert abs(b["u_damage"] - a["u_damage"]) <= EPS, (
        f"la feuille DamageDealt a bouge ({a['u_damage']:.6f} -> {b['u_damage']:.6f}) : le cran "
        f"n'ISOLE PAS l'overkill")
    assert abs(b["u_kill"] - a["u_kill"]) <= EPS, (
        f"la feuille KillUnit a bouge ({a['u_kill']:.6f} -> {b['u_kill']:.6f}) : le cran n'ISOLE "
        f"PAS l'overkill")
    assert abs(b["u_overkill"] - a["u_overkill"]) > EPS, (
        f"la feuille OverkillUnit n'a PAS bouge ({a['u_overkill']:.6f}) : le cran ne mesure rien")
