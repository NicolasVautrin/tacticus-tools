"""Fixtures locales a la tranche RUNNER.

`psychic_aoe_case` — MONTAGE NOMME ET REUTILISABLE des deux AoE Psychic (PlagueWind 1035 /
Doombolt 1102). Le montage lui-meme (build isole, drive des positions des DEUX camps, capture
`decisionView`/`observeBattle`/`combatSnapshot`/`boardGraph`/`dumpRng`, replay OFFLINE sur le MEME
etat et le MEME `state.rng`, cast LIVE, comparaison per-coup, contre-epreuve de discriminance) vit
dans `scripts/python/probe_psychic_aoe.py` — la fixture n'est que sa PORTE pytest : un seul point
qui traduit « harnais indisponible » en skip (converti en ECHEC par le conftest racine) et qui garde
les tests lisibles.

Consommateurs : `test_plague_wind_live.py`, `test_doombolt_live.py`. Ajouter un cas = ajouter une
entree dans `probe_psychic_aoe.CASES`, pas dupliquer un montage inline dans un test.

`overkill_gate_case` (#178, etendue #R33) — meme forme : la PORTE pytest du montage A de
`scripts/python/probe_178_overkill_gate.py`, qui mesure les ARGUMENTS de la surcharge d'instance de
`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`. Deux PAIRES : (`control` / `titus`) pour
les gates d'unite (`CanBeOverkilled`, `PreventOverkill`) et (`crit` / `nocrit`) pour `isCritical`.
Dans chaque paire on tue avec la MEME attaque, le MEME degat et les MEMES PV -- une seule variable
change. `overkill_revive_case` (#R33) = le montage B, a observable INDEPENDANT (porte revive
`Narthecium` « unless Overkilled ») et tueur SANS `ThrillSeekers`, qui ATTRIBUE l'observation a
`isCritical` puis isole `isForceOverkill` (regime `revive-flail`). Consommateur des deux :
`test_overkill_gate_live.py`.

`overkill_decision_source_case` / `overkill_decision_utility_case` / `overkill_decision_rank_case`
(#R34) — MEME forme, MEME endroit, mais sur la face DECISION de l'overkill : ce ne sont PAS des
jumelles du montage crescendo (qui mesure le chokepoint de MORT), elles mesurent le canal
`MightCrit@+0xb1` -> `MightBeOverkill` -> `PossibleOverkill` (utilite 37). Les trois etages vivent
dans `scripts/python/probe_r34_overkill_decision.py` : SOURCE du flag (`CouldCrit(attaquant)` +
producteur offline), CANAL d'utilite (formule ISOLEE : les deux cotes sur predictions NATIVES,
scoreur natif = `pairUtility`), CLASSEMENT (bascule d'argmax entre deux cibles). Consommateur :
`test_overkill_decision_live.py`."""
from __future__ import annotations

import pytest

import probe_psychic_aoe as P
import probe_178_overkill_gate as OVK
import probe_r34_overkill_decision as DEC
import probe_195_prevent_overkill_decision as PVO
import probe_o5_unit_flags as O5
import probe_294_trigger_ability_channels as TAC


@pytest.fixture
def psychic_aoe_case(live_session):
    """Fabrique : `psychic_aoe_case("pw-chain")` -> le dict de resultats du probe.

    `live_session` est tire ICI (le montage exige la session Frida) ; le runner est DISPOSE par le
    probe lui-meme en sortie de `run()`, donc rien a liberer au teardown. `seed`/`board` sont
    surchargeables pour rejouer un cas sur un second couple (discipline de generalisation)."""
    def _build(case: str, seed: str = "31337", board_id: str = "MC1_67") -> dict:
        assert case in P.CASES, f"cas inconnu : {case} (connus : {sorted(P.CASES)})"
        r = P.run(case, seed=seed, board_id=board_id, verbose=True)
        if "error" in r:
            pytest.skip(f"build runner KO / harnais indisponible ({case}): {r['error']}")
        return r
    return _build


@pytest.fixture(scope="module")
def overkill_gate_case(live_session):
    """Fabrique : `overkill_gate_case("titus")` -> le dict de mesure du probe #178.

    Portee MODULE : les deux regimes de la paire sont montes une fois pour tout le fichier de test
    (chaque regime = un build + un drive + une attaque letale). `live_session` est tire ICI (le
    montage exige la session Frida) ; le runner est DISPOSE par le probe en sortie de `run()`.

    ⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268). Un `pytest.skip` sur un
    regime non atteint est un VERT qui ment : aucune mesure n'a eu lieu, et la suite ne rougit pour
    personne. C'est exactement ce qui a masque 8 tests de cette famille pendant toute la migration
    de build."""
    cache: dict = {}

    def _case(case: str, seed: int = 17811) -> dict:
        assert case in OVK.CASES, f"cas inconnu : {case} (connus : {sorted(OVK.CASES)})"
        if case not in cache:
            r = OVK.run(case, seed=seed, verbose=True)
            if "error" in r:
                pytest.fail(f"montage overkill-gate NON INSTALLE ({case}): {r['error']}")
            cache[case] = r
        return cache[case]
    return _case


@pytest.fixture(scope="module")
def overkill_revive_case(live_session):
    """Fabrique : `overkill_revive_case("revive-crit")` -> le dict du montage B du probe #178/#R33.

    Observable INDEPENDANT du crescendo (`Narthecium_ReviveEffect` revive « unless Overkilled ») et
    tueur SANS le trait `ThrillSeekers` -> c'est ce montage qui ATTRIBUE l'overkill au flag
    `isCritical` plutot qu'au rider ThrillSeekers. Portee MODULE (un build par regime).

    Meme regle qu'au-dessus : montage non installe => ECHEC, jamais skip (#268)."""
    cache: dict = {}

    def _case(case: str, seed: int = 17833) -> dict:
        assert case in OVK.REVIVE_CASES, \
            f"cas inconnu : {case} (connus : {sorted(OVK.REVIVE_CASES)})"
        if case not in cache:
            r = OVK.run_revive(case, seed=seed, verbose=True)
            if "error" in r:
                pytest.fail(f"montage overkill-revive NON INSTALLE ({case}): {r['error']}")
            cache[case] = r
        return cache[case]
    return _case


# ── #R34 — face DECISION de l'overkill (`MightBeOverkill` lit `MightCrit@+0xb1`) ────────────────

@pytest.fixture(scope="module")
def overkill_decision_source_case(live_session):
    """SOURCE du flag : `pred.mightCrit` LIVE vs `CouldCrit(attaquant)` (stats `combatSnapshot`) ET
    producteur OFFLINE (`composite_fields()["mightCrit"]`) vs le flag de l'event NATIF.

    TROIS regimes de crit -- `100,1` (les deux conjonctions vraies), `100,0` et `0,1` (une seule) :
    c'est ce qui interdit de conclure d'une correlation triviale « tout a 1 / tout a 0 ». Portee
    MODULE (un build par regime)."""
    cache: dict = {}

    def _case(seed: int = 34011) -> dict:
        if "r" not in cache:
            cache["r"] = DEC.run_source(
                seed=seed, verbose=True,
                regimes=(("crit-on", "100,1"), ("chance-only", "100,0"), ("dmg-only", "0,1")))
        return cache["r"]
    return _case


@pytest.fixture(scope="module")
def overkill_decision_utility_case(live_session):
    """CANAL d'utilite, formule ISOLEE : les DEUX cotes sont nourris des MEMES predictions NATIVES
    (`aiPlaybookPredict`), le natif etant le scoreur invoque en direct (`pairUtility`). Regime
    LETAL SOUS LE SEUIL impose et VERIFIE. Portee MODULE (3 builds : tune + 2 regimes)."""
    cache: dict = {}

    def _case(seed: int = 34101) -> dict:
        if "r" not in cache:
            r = DEC.run_utility(seed=seed, verbose=True)
            if "error" in r:
                pytest.skip(f"montage overkill-decision KO : {r['error']}")
            cache["r"] = r
        return cache["r"]
    return _case


@pytest.fixture(scope="module")
def overkill_decision_rank_case(live_session):
    """CLASSEMENT : deux cibles descendues dans DEUX bandes d'overkill differentes -> l'argmax du
    port d'AVANT (`isCritical = 0`) et celui du natif DIVERGENT, et le port d'APRES rejoint le
    natif. Le pas de descente est du meme ordre que la largeur de bande -> le probe re-tente sur
    plusieurs seeds. Portee MODULE (couteux : 2 builds + une descente pilotee par seed essaye)."""
    cache: dict = {}

    def _case(seed: int = 34201) -> dict:
        if "r" not in cache:
            r = {}
            for k in (0, 7, 13, 29):
                r = DEC.run_rank(seed=seed + k, verbose=True)
                if r.get("flip") or r.get("error"):
                    break
            if r.get("error"):
                pytest.skip(f"montage overkill-rank KO : {r['error']}")
            cache["r"] = r
        return cache["r"]
    return _case


# ── #195 — l'AUTRE argument de la face DECISION (`isPreventOverkill` = result@+0xb3) ────────────

@pytest.fixture(scope="module")
def prevent_overkill_channel_case(live_session):
    """CANAL : `preventOverkill` prend-il DEUX valeurs ? Meme runner, meme attaquant, deux cibles --
    `ultraTitus` (porteur du flag 0x13) et `genesPrimus` (temoin). Sans deux valeurs distinctes, le
    champ est INDISCERNABLE d'un champ mort et aucun test d'egalite ne peut faire la difference.
    Portee MODULE (un seul build pour les deux cibles)."""
    cache: dict = {}

    def _case(seed: int = 19501) -> dict:
        if "r" not in cache:
            cache["r"] = PVO.run_canal(seed=seed, verbose=True)
        return cache["r"]
    return _case


@pytest.fixture(scope="module")
def prevent_overkill_utility_case(live_session):
    """UTILITE, formule ISOLEE (meme forme que `overkill_decision_utility_case`, autre argument) :
    `pairUtility` NATIF vs le terme degat du PORT nourri des MEMES events natifs, en variante AVEC
    et SANS la cle `preventOverkill`. Regime LETAL SOUS LE SEUIL + crit force, tune par cible (les
    bornes RAW dependent de la cible). Portee MODULE (2 builds par cible : tune + mesure).

    ⚠ ECHEC, jamais skip (#268) : ce montage lit les bornes RAW **et** `preventOverkill` dans le
    struct de prediction decode par les hooks. Quand ce decodeur derape, le montage ne peut plus
    rien mesurer -- et un skip transformerait cette panne d'INSTRUMENT en vert silencieux. Le
    message d'erreur du probe distingue explicitement « canal mort » de « regime inatteignable »."""
    cache: dict = {}

    def _case(victim: str, seed: int = 19601) -> dict:
        if victim not in cache:
            r = PVO.run_utility(victim, seed=seed, verbose=True)
            if r.get("error"):
                pytest.fail(f"montage prevent-overkill NON INSTALLE ({victim}) : {r['error']}")
            cache[victim] = r
        return cache[victim]
    return _case


# ── O5 — `UnitFlagsComponent` expose live (`combatSnapshot.unitFlags`) ──────────────────────────

@pytest.fixture(scope="module")
def unit_flags_accord_case(live_session):
    """ACCORD A TROIS SOURCES sur `UnitFlag.PreventOverkill` (=19) : la lecture ECS neuve
    (`combatSnapshot.unitFlags`), la DERIVATION par l'effet actif 1354 (`effects_prevent_overkill`,
    la voie que le port empruntait faute de canal) et le `preventOverkill` de l'event natif
    (`result@+0xb3`, #190). Porteur `ultraTitus` / temoin `genesPrimus`. C'est cet accord qui
    autorise a SUBSTITUER la lecture a la derivation. Portee MODULE (un seul build)."""
    cache: dict = {}

    def _case(seed: int = 50101) -> dict:
        if "r" not in cache:
            r = O5.run_accord(seed=seed, verbose=True)
            if r.get("error"):
                pytest.skip(f"montage unit-flags KO : {r['error']}")
            cache["r"] = r
        return cache["r"]
    return _case


# ── #294 — les DEUX canaux `AbilityEntities` (`+0x60` CurrentAbility / `+0x98` TriggeringAbility) ──

@pytest.fixture
def trigger_ability_channel_case():
    """Fabrique : `trigger_ability_channel_case()` -> le montage NOMINAL, `(...,"before")` -> une
    contre-epreuve. Rend le dict de trace de `probe_294_trigger_ability_channels.run()`.

    MONTAGE NOMME ET REUTILISABLE de la SEPARATION des deux canaux : une chaine
    `A --On(0xd)--> B --On(9)--> C` de triggered-abilities espionnes, montee dans un `State` nu.
    C'est le seul montage connu ou `+0x60` et `+0x98` portent deux valeurs NON NULLES DIFFERENTES
    (dans le behaviour de B : `+0x60 = B`, `+0x98 = A`) -- un montage a une seule triggered les
    laisse tous deux a `this.Id` et ne prouve donc RIEN.

    PAS de `live_session`, et c'est DELIBERE : le canal `+0x98` n'a aujourd'hui aucun consommateur
    porte (aucune ability n'ecoute `On(0xd = UnitTriggeredAbility)`) ni aucun capteur live, donc
    aucune observable de bataille n'en depend. Un montage live serait du theatre. Ce qui est
    verrouille ici est OFFLINE, deterministe et sans RNG : le MOMENT D'ECRITURE de chaque canal et
    sa PORTEE. Le jour ou une ability ecoutera cet evenement, ce montage est la porte a reutiliser.

    Quatre contre-epreuves rejouables (`probe_294_trigger_ability_channels.MUTATIONS`), chacune
    neutralisant une moitie du port : `before` (ecriture avant le behaviour), `alias` (le piege
    nomme par `case-292` : reutiliser `state.triggering_ability`), `persist` (pas de restauration),
    `noevent` (pas d'`On(0xd)`)."""
    def _case(mutate: str = None) -> dict:
        assert mutate in (None,) + TAC.MUTATIONS, \
            f"mutation inconnue : {mutate} (connues : {sorted(TAC.MUTATIONS)})"
        return TAC.run(mutate=mutate, verbose=False)
    return _case


@pytest.fixture(scope="module")
def unit_flags_moved_case(live_session):
    """LE CANAL SUIT L'ETAT : `UnitFlag.Moved` (=0) sur la MEME unite, avant puis apres un
    `MoveUnitOperation` reel. Sans cette garde, une table de flags FIGEE au build passerait la
    garde d'accord (le porteur porte son flag des le deploiement et ne le lache jamais). Portee
    MODULE (un build + un mouvement)."""
    cache: dict = {}

    def _case(seed: int = 50201) -> dict:
        if "r" not in cache:
            cache["r"] = O5.run_moved(seed=seed, verbose=True)
        return cache["r"]
    return _case
