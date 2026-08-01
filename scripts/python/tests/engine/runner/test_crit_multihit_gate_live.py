"""#366-r1-crit-multihit -- LE cliquet qui manquait : une salve MULTI-COUPS a crit NON NUL.

Ce que ce fichier retient, et qu'AUCUN test ne retenait :

    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` n'appelle `RollCritical` qu'au coup
    qui SUIT un coup CRITIQUE. Des qu'un coup ne crite pas, la boucle recalcule
    `OngoingHitGroup+0x3c` (`isCriticalDamageAllowed`, le 5e parametre NOMME de
    `IdunBattle.Operations.ADamageOperation$$SetupHitGroup`) par
    `options[+0x40]?.Any(hitIndex => hitIndex == i + 1) ?? false` -- NUL pour l'attaque normale --,
    ce qui arme DEFINITIVEMENT le flag « never crit » du message (`options[+0x29] |= ...`, monotone).
    Le port roulait un crit-roll a CHAQUE coup : il consommait donc jusqu'a `hits` tirages de trop,
    et TOUT le per-coup se decalait a partir du 3e coup.

Le montage exercerait donc RIEN s'il ne prouvait pas d'abord que le regime est DISCRIMINANT :
`test_regime_is_discriminant` exige au moins un CRIT **suivi** d'un non-crit dans la meme salve
(c'est exactement ce que `--crit 100,x`, le seul regime crit teste jusqu'ici, ne peut pas produire).

Le cliquet porte sur les DEUX etages, pas sur un scalaire :
  (a) le NOMBRE de tirages -- `dumpRng.mti` avant/apres cote natif contre le `mti` du port apres
      rejeu sur le MEME etat MT (deux modeles qui consomment autant de `genrand_int32` finissent au
      MEME index : oracle EXACT) ;
  (b) la VALEUR de chaque coup -- per-coup live == per-coup offline, bit a bit.

Et il porte sa propre CONTRE-EPREUVE : `crit_gate_open` force a True (= le port d'AVANT ce cas)
doit FAIRE DIVERGER le rejeu. Une garde qu'on ne sait pas faire echouer ne garde rien.

Montage (probe `probe_366r1_crit_multihit.py`, qui porte le drive et le replay) :
  * attaquant MULTI-COUPS sans rapport avec aucune ability crit -- `necroDestroyer` (6 coups) ;
  * `--crit 50,700` : `GetStat(9) = 50` -> des crits tombent, puis s'arretent ;
  * `--block-target 0,0` : aucun block, donc aucun tirage tiers dans le flux ;
  * distance 1 (melee), unites DEPLACEES jusqu'a la portee -- jamais « bloque par le spawn ».
"""
from __future__ import annotations

import pytest

import probe_366r1_crit_multihit as P

ATTACKER = "necroDestroyer"          # 6 coups -- AUCUN rapport avec une ability de crit
P_UNITS = "necroDestroyer,ultraApothecary"
A_UNITS = "necroWarden,necroOverlord"   # ni Overwatch, ni Parry/Camouflage (pas de -coup)
CRIT = "50,700"                       # regime a EXTINCTION INTERNE (cf. docstring)


def _case(rpc, build_runner, seed, board, crit=CRIT, attacker=ATTACKER,
          p_units=P_UNITS, mutate=None):
    b = build_runner(seed, extra=["--board", board, "--p-units", p_units,
                                  "--a-units", A_UNITS, "--crit", crit,
                                  "--block-target", "0,0"])
    m = P.measure(lambda meth, body=None, t=120: rpc(meth, body, t),
                  b["rid"], attacker, dist=1, mutate=mutate)
    if m.get("error"):
        pytest.fail("montage KO (ce n'est PAS un skip vert) : %s" % m["error"])
    return m


@pytest.fixture(scope="module")
def case_mc1(rpc, build_runner):
    """Couple 1 : MC1_67 / seed 777."""
    return _case(rpc, build_runner, "777", "MC1_67")


@pytest.fixture(scope="module")
def case_c1(rpc, build_runner):
    """Couple 2 : C1_25 / seed 31337, `--crit 35,700` (le regime ou l'extinction tombe au 3e coup
    sur CE flux -- a 50 les six coups critent et le montage cesserait d'etre discriminant)."""
    return _case(rpc, build_runner, "31337", "C1_25", crit="35,700")


# --------------------------------------------------------------- garde-fous du montage
@pytest.mark.parametrize("fx", ["case_mc1", "case_c1"])
def test_regime_is_discriminant(fx, request):
    """Sans un CRIT suivi d'un NON-CRIT dans la meme salve, ce fichier ne prouverait RIEN :
    c'est precisement le trou par lequel le residu a survecu (les tests crit existants tournent
    a `--crit 100,x`, ou aucun coup ne peut eteindre le canal)."""
    m = request.getfixturevalue(fx)
    crits = m["crits"]
    assert len(crits) >= 3, "salve trop courte pour discriminer : %s" % (crits,)
    assert any(crits), "aucun crit -> le canal n'est pas exerce (crits=%s)" % (crits,)
    assert not all(crits), "tous les coups critent -> l'extinction n'est pas exercee"
    first_false = crits.index(False)
    assert first_false > 0, "le 1er coup ne crite pas -> l'extinction tombe avant d'etre visible"
    assert not any(crits[first_false:]), (
        "un crit APRES le premier non-crit : le natif ne re-tire jamais (crits=%s)" % (crits,))


# --------------------------------------------------------------- etage (a) : les TIRAGES
@pytest.mark.parametrize("fx", ["case_mc1", "case_c1"])
def test_draw_count_matches_live(fx, request):
    """ETAGE (a) : le port consomme EXACTEMENT autant de `genrand_int32` que le natif.
    Mesure directe : `mti` (index MT, +1 par tirage) avant/apres cote natif contre le `mti` du
    port apres rejeu depuis le MEME `mt[624]`/`mti`."""
    m = request.getfixturevalue(fx)
    assert m["d_mti_live"] == m["d_mti_port"], (
        "flux de tirages desaligne : natif=%d port=%d (crits=%s)"
        % (m["d_mti_live"], m["d_mti_port"], m["crits"]))


@pytest.mark.parametrize("fx", ["case_mc1", "case_c1"])
def test_draw_count_is_two_then_one(fx, request):
    """La LOI, pas seulement l'accord : `1 tirage par coup` + `1 crit-roll par coup CRITIQUE`
    + `1 crit-roll pour le premier coup non-critique` (celui qui eteint le canal)."""
    m = request.getfixturevalue(fx)
    crits = m["crits"]
    attendu = len(crits) + sum(1 for c in crits if c) + (0 if all(crits) else 1)
    assert m["d_mti_live"] == attendu, (
        "loi de consommation contredite : natif=%d attendu=%d (crits=%s)"
        % (m["d_mti_live"], attendu, crits))


# --------------------------------------------------------------- etage (b) : les VALEURS
@pytest.mark.parametrize("fx", ["case_mc1", "case_c1"])
def test_per_hit_bit_exact(fx, request):
    """ETAGE (b) : per-coup offline == per-coup live, bit a bit, sur TOUTE la salve."""
    m = request.getfixturevalue(fx)
    assert m["live"], "aucun event de degat live"
    assert m["port"] == m["live"], (
        "per-coup offline != live\n  live=%s\n  port=%s\n  crits=%s"
        % (m["live"], m["port"], m["crits"]))


# --------------------------------------------------------------- contre-epreuve
def test_mutation_nogate_diverges(rpc, build_runner):
    """CONTRE-EPREUVE : gate toujours ouvert = le port d'AVANT ce cas (un crit-roll par coup).
    Il doit consommer PLUS de tirages que le natif ET produire un per-coup DIFFERENT -- sinon la
    garde ci-dessus passerait aussi sur un port faux."""
    m = _case(rpc, build_runner, "777", "MC1_67", mutate="nogate")
    assert m["d_mti_port"] > m["d_mti_live"], (
        "la mutation ne consomme pas plus de tirages (natif=%d mute=%d) -> non discriminante"
        % (m["d_mti_live"], m["d_mti_port"]))
    assert m["port"] != m["live"], (
        "la mutation reproduit quand meme le live -> la garde ne prouve rien (live=%s)"
        % (m["live"],))


# --------------------------------------------------------------- second PORTEUR
def test_second_carrier_melee(rpc, build_runner):
    """Le mecanisme n'est PAS propre a `necroDestroyer` : meme loi sur `eldarMauganRa` (5 coups
    melee), le porteur sur lequel le residu avait ete releve la premiere fois."""
    m = _case(rpc, build_runner, "777", "MC1_67",
              attacker="eldarMauganRa", p_units="eldarMauganRa,ultraApothecary")
    crits = m["crits"]
    assert any(crits) and not all(crits), "regime non discriminant sur ce porteur : %s" % (crits,)
    assert m["d_mti_live"] == m["d_mti_port"], (
        "flux desaligne sur le 2e porteur : natif=%d port=%d" % (m["d_mti_live"], m["d_mti_port"]))
    assert m["port"] == m["live"], (
        "per-coup != live sur le 2e porteur\n  live=%s\n  port=%s" % (m["live"], m["port"]))


# --------------------------------------------------------------- non-regression crit NUL
def test_zero_crit_unchanged(rpc, build_runner):
    """NON-REGRESSION du regime historique (`--crit 0,x`) : aucun crit possible, donc AUCUN
    crit-roll -- 1 tirage par coup, exactement comme avant ce cas."""
    m = _case(rpc, build_runner, "777", "MC1_67", crit="0,700")
    assert not any(m["crits"]), "un crit a cc=0 : %s" % (m["crits"],)
    assert m["d_mti_live"] == len(m["live"]) == m["d_mti_port"], (
        "a cc=0 le flux doit valoir 1 tirage/coup : natif=%d port=%d n=%d"
        % (m["d_mti_live"], m["d_mti_port"], len(m["live"])))
    assert m["port"] == m["live"], "per-coup != live a cc=0 : %s vs %s" % (m["port"], m["live"])
