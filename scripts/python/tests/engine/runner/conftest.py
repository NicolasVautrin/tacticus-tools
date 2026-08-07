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
import probe_334_defend_the_divine_work as DTDW
import probe_r34_overkill_decision as DEC
import probe_195_prevent_overkill_decision as PVO
import probe_o5_unit_flags as O5
import probe_294_trigger_ability_channels as TAC
import probe_301_kill_unit_trigger_channels as KUC
import probe_306_effect_trigger_channels as EFC
import probe_338_ai_target_choice as AITC
import probe_348_ai_approach as AIAP
import probe_270d_lysander_deploy as LYS
import probe_357_relic_rail as RELIC
import probe_363_ability_states_channel as ASD
import probe_487_hellfyre_missile_rack as HFMR


@pytest.fixture
def hellfyre_case(live_session):
    """Fabrique : `hellfyre_case(arm=True)` -> le dict de mesure du probe #487.

    Meme forme que `psychic_aoe_case` : `live_session` est tire ICI (le montage exige la session
    Frida), le runner est DISPOSE par le probe en sortie de `run()`. `arm` choisit le regime
    (armement Psychic par Doombolt, ou cast SEUL = contre-cas volet 2 vide), `target_mode` choisit
    si la cible de Hellfyre est elle-meme ARMEE ou le TEMOIN hors Psychic ; `seed`/`board` sont
    surchargeables pour rejouer sur un second couple (discipline de generalisation).

    ⚠ `seed` ne fait PAS varier le MT du runner (mesure #487) -- ce qui exerce reellement le tirage,
    c'est l'ETAT du MT au cast, donc le CHOIX DU REGIME, pas le seed."""
    def _build(arm: bool = True, seed: str = "777", board_id: str = "MC1_67",
               target_mode: str = "armed") -> dict:
        r = HFMR.run(arm=arm, seed=seed, board_id=board_id, target_mode=target_mode, verbose=True)
        if "error" in r:
            pytest.skip("build runner KO / harnais indisponible "
                        f"(hellfyre arm={arm} target={target_mode}): {r['error']}")
        return r
    return _build


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


# ── #301 — les memes DEUX canaux, mais sur le vecteur MORT (`KillUnitOperation$$Execute`) ─────────

@pytest.fixture
def kill_unit_trigger_channel_case():
    """Fabrique : `kill_unit_trigger_channel_case()` -> le montage NOMINAL (qui exerce le
    `_verify_deaths` DU DEPOT), `(mutate="legacy")` -> une contre-epreuve. Rend le dict de trace de
    `probe_301_kill_unit_trigger_channels.run()`.

    MONTAGE NOMME de l'AUTRE ecrivain de `+0x98` : `IdunBattle.Operations.KillUnitOperation$$Execute`
    memset son `AbilityEntities` puis n'y reecrit QUE le bloc `+0x98..+0xb4` (copie de
    `KillUnitOptions+0x04` = le `killTrigger` de la file), et publie CETTE struct sur ses cinq
    evenements -- donc `CurrentAbility` (`+0x60`) est VIDE sur tout le vecteur mort.

    Le mode NOMINAL passe `real=True` : aucun drain de substitution, c'est le code du depot qui est
    sous test. C'est ce mode qui a donne son ROUGE au fix (avant #301 : `+0x60 = killTrigger`,
    `+0x98` vide -- l'inverse exact du natif).

    Quatre contre-epreuves (`probe_301_kill_unit_trigger_channels.MUTATIONS`), chacune avec sa
    signature propre : `legacy` (l'etat d'avant #301), `both` (les deux canaux alimentes),
    `nowipe` (`+0x60` non efface -> l'ambiant fuit dans la mort), `persist` (pas de restauration)."""
    def _case(mutate: str = None) -> dict:
        assert mutate in (None,) + KUC.MUTATIONS, \
            f"mutation inconnue : {mutate} (connues : {sorted(KUC.MUTATIONS)})"
        return KUC.run(mutate=mutate, verbose=False, real=mutate is None)
    return _case


# ── #306 — les memes DEUX canaux, mais sur les vecteurs d'EFFET (pose / retrait) ──────────────────

@pytest.fixture
def effect_trigger_channel_case():
    """Fabrique : `effect_trigger_channel_case()` -> le montage NOMINAL (qui exerce le foyer DU
    DEPOT : `AddEffectOperation.execute` reel + la feuille DSL `RemoveEffect` reelle),
    `(mutate="symmetric")` -> une contre-epreuve, `(add_only=True)` -> la face POSE seule. Rend le
    dict de trace de `probe_306_effect_trigger_channels.run()`.

    MONTAGE NOMME de l'ASYMETRIE : les deux Operations d'effet batissent leur `AbilityEntities` par
    `memset(0, 0x128)`, mais `IdunBattle.Operations.AddEffectOperation$$Execute` remplit
    `currentAbilityOrEffect` (`+0x60`) **ET** `triggerAbilityOrEffect` (`+0x98`) avec le meme
    `AbilityOrEffect(effectType)`, tandis que `IdunBattle.Operations.RemoveEffectOperation$$Execute`
    n'ecrit que `+0x60` -- `+0x98` reste a ZERO. Donc sur `On(63 = PreEffectRemoved)` / `On(64 = EffectRemoved)`, c'est
    `CurrentAbilityIs` qui porte l'effet retire, jamais `TriggeringEffectIs`.

    PAS de `live_session`, et c'est DELIBERE -- meme raison qu'en #294/#301 : aucun consommateur
    porte n'ecoute les vecteurs de retrait, et sur la POSE les deux canaux portent la MEME valeur,
    donc aucune observable de bataille ne separe les deux lectures. Ce qui est verrouille ici est
    OFFLINE, deterministe et sans RNG : QUEL canal chaque Operation ecrit, et sa PORTEE. La
    non-regression du COMPORTEMENT, elle, est portee par `test_lot_pose_live.py` (le seul
    consommateur porte de `On(61 = PreEffectAdded)`).

    Quatre contre-epreuves (`probe_306_effect_trigger_channels.MUTATIONS`), chacune avec sa
    signature propre : `legacy` (l'etat d'avant #306 : la pose n'ecrit que `+0x98`, le retrait
    n'emet rien), `symmetric` (le retrait ecrit `+0x98` comme la pose), `noambient` (l'ambiant
    d'une triggered englobante n'est pas ecrase par le memset), `persist` (pas de restauration)."""
    def _case(mutate: str = None, add_only: bool = False) -> dict:
        assert mutate in (None,) + EFC.MUTATIONS, \
            f"mutation inconnue : {mutate} (connues : {sorted(EFC.MUTATIONS)})"
        return EFC.run(mutate=mutate, verbose=False, add_only=add_only)
    return _case


# ── #334 — face COMBAT de `DefendTheDivineWork` (1117), les DEUX Operations enchainees ───────────

@pytest.fixture(scope="module")
def defend_the_divine_work_case(build_runner, rpc):
    """Fabrique : `defend_the_divine_work_case("repair")` -> le dict de mesure du montage #334.

    PORTE pytest du montage de `scripts/python/probe_334_defend_the_divine_work.py` (build isole,
    conduite des positions des DEUX camps, capture + `dumpRng`, cast OFFLINE sur cette capture puis
    cast LIVE). TROIS regimes, et c'est leur CONTRASTE qui prouve quelque chose :

      `repair`  etage 1 seul (les camps restent loin : aucune attaque ne peut masquer un ecart) ;
      `attack`  l'ALLIE adjacent au contact d'un ennemi, le caster non -> l'etage 2 DOIT mordre ;
      `caster`  le CASTER au contact d'un ennemi, l'allie adjacent non -> l'etage 2 ne doit RIEN
                faire, et `normal_targets` etablit que le caster POUVAIT frapper.

    Portee MODULE (chaque regime = un build + une conduite de positions + deux casts).
    ⚠ Montage non installe => ECHEC, jamais skip (#268) : un skip serait un vert qui ment."""
    cache: dict = {}

    def _case(scenario: str = "repair") -> dict:
        if scenario not in cache:
            # `keep=True` : le runner appartient a `build_runner`, qui le libere au teardown du
            # module -- le probe ne doit pas le disposer sous les pieds de son proprietaire.
            r = DTDW.run_scenario(rpc, scenario, build_runner=build_runner, keep=True)
            if not r.get("ok"):
                pytest.fail("montage DefendTheDivineWork NON INSTALLE (%s) : %s"
                            % (scenario, r.get("why")))
            cache[scenario] = r
        return cache[scenario]

    return _case


# ── #338 — le CHOIX DE CIBLE de `PerformAIAbilityUnitBehaviour$$Execute` ─────────────────────────

@pytest.fixture(scope="module")
def ai_target_choice_case(build_runner, rpc):
    """Fabrique : `ai_target_choice_case("orksKillaKan")` -> le dict de mesure du montage #338.

    PORTE pytest de `scripts/python/probe_338_ai_target_choice.py` : DEUX ennemis a distance EGALE
    de la tuile de spawn d'un summon melee (`AberrantHypermorph` 1166), avec des `maxHP` d'un ordre
    de grandeur d'ecart. Le raccourci historique (`_nearest_enemy`) ne peut les departager que par
    son tie-break `id` ; le moteur d'utilite, lui, suit le `maxHP`. Le parametre est le visualId de
    l'ennemi a PETIT maxHP -- l'echanger doit faire BASCULER la victime, live comme offline.

    Portee MODULE (chaque regime = un build + une conduite de position + deux casts).
    ⚠ Montage non installe => ECHEC, jamais skip (#268)."""
    cache: dict = {}

    def _case(low_vis: str) -> dict:
        if low_vis not in cache:
            # `keep=True` : le runner appartient a `build_runner` (teardown du module).
            r = AITC.run(rpc, low_vis=low_vis, build_runner=build_runner, keep=True)
            if not r.get("ok"):
                pytest.fail("montage AI-target-choice NON INSTALLE (low=%s) : %s"
                            % (low_vis, r.get("why")))
            cache[low_vis] = r
        return cache[low_vis]

    return _case


# ── #348 — l'APPROCHE d'un acteur de free-attack (`+0x78 moveAmount = null`) ─────────────────────

@pytest.fixture(scope="module")
def ai_approach_case(build_runner, rpc):
    """Fabrique : `ai_approach_case("approach"|"stay"|"move_only")` -> le dict de mesure du montage
    #348.

    PORTE pytest de `scripts/python/probe_348_ai_approach.py` : `ForwardSpotter` (1143, MoW
    `astraOrdnanceBattery`) pose un guardsman sur une tuile libre ADJACENTE A UN ALLIE CHOISI (masque
    `TargetIsFriendly`), donc la distance spawn<->ennemi est ENTIEREMENT pilotable. Le regime nomme
    la fenetre : `approach` (3..5 = hors portee d'arme mais a portee apres deplacement), `stay`
    (<= 2 = deja a portee), `move_only` (>= 6 = deplacement pur).

    Portee MODULE (chaque regime = un build + une conduite de positions + un cast).
    ⚠ Montage non installe => ECHEC, jamais skip (#268)."""
    cache: dict = {}

    def _case(regime: str) -> dict:
        if regime not in cache:
            # `keep=True` : le runner appartient a `build_runner` (teardown du module).
            r = AIAP.run(rpc, regime=regime, build_runner=build_runner, keep=True)
            if not r.get("ok"):
                pytest.fail("montage AI-approach NON INSTALLE (regime=%s) : %s"
                            % (regime, r.get("why")))
            cache[regime] = r
        return cache[regime]

    return _case


# ── #270-d — un trait hors `UnitTrait` rend le BC ENTIER indeserialisable ────────────────────────

@pytest.fixture(scope="module")
def lysander_deploy_case(live_session):
    """Fabrique : `lysander_deploy_case()` -> le dict de mesure du montage #270-d.

    PORTE pytest de `scripts/python/probe_270d_lysander_deploy.py` : DEUX builds a UN SEUL BIT
    d'ecart -- meme roster (`astarLysander` vs `orksWarboss,orksNob,necroWarden,eldarRanger`), meme
    board (MC1_67), meme seed, meme seed BC augmente. Seule difference : le bras A RE-INSERE
    `ImperialFists` dans `BC.Units[astarLysander].Traits`.

    Ce que le contraste etablit : `UnitConfiguration.Traits` est TYPE
    `List<IdunBattle.Entities.Enum.UnitTrait>` (`BattleConfigBuilder$$GetUnitConfiguration` recopie
    `UnitProperties+0x18`, que `UnitPropertiesExtensions$$GetPlayerFacingTraits` lit en rendant
    `List<UnitTrait>`), donc un nom hors enum fait LEVER
    `Newtonsoft.Json.Utilities.EnumUtils$$ParseEnum` au step=deserialize BC d'`initAndStart`. Un
    seul bras suffirait a montrer « ca marche » ou « ca casse » ; c'est la PAIRE qui attribue.

    Portee MODULE (deux builds). ⚠ Montage non installe => ECHEC, jamais skip (#268) : ici un skip
    serait particulierement trompeur -- « le porteur ne se deploie pas » est justement l'etat
    qu'on est en train de refuter."""
    cache: dict = {}

    def _case(seed: int = 777, board: str = "MC1_67") -> dict:
        key = (seed, board)
        if key not in cache:
            r = LYS.run(seed=seed, board=board, verbose=True)
            if r.get("why"):
                pytest.fail("montage lysander-deploy NON INSTALLE : %s" % r["why"])
            cache[key] = r
        return cache[key]

    return _case


@pytest.fixture(scope="module")
def trait_hors_enum_cross_case(live_session):
    """Fabrique : `trait_hors_enum_cross_case("votanChampion")` -> la CONTRE-EPREUVE CROISEE #270-d.

    Le A/B de `lysander_deploy_case` montre que RETIRER `ImperialFists` deverrouille
    `astarLysander` ; il n'exclut pas que la faute vienne d'autre chose de propre a cette unite (son
    kit, son passif, son rang) dont le trait n'aurait ete qu'un co-facteur. Cette fixture prend une
    unite qui monte DEJA et lui POSE le meme nom hors enum : si elle casse a son tour, la cause est
    le TRAIT, pas le porteur.

    Portee MODULE (deux builds par unite). ⚠ Montage non installe => ECHEC, jamais skip (#268)."""
    cache: dict = {}

    def _case(porteur: str = "votanChampion", seed: int = 777, board: str = "MC1_67") -> dict:
        key = (porteur, seed, board)
        if key not in cache:
            r = LYS.run_cross(porteur, seed=seed, board=board, verbose=True)
            if r.get("why"):
                pytest.fail("contre-epreuve croisee NON INSTALLEE : %s" % r["why"])
            cache[key] = r
        return cache[key]

    return _case


# ── #357 — le rail de la relique EQUIPEE (`BC.Units[].TertiaryAbility`) ──────────────────────────

@pytest.fixture(scope="module")
def relic_rail_case(build_runner, rpc):
    """Fabrique : `relic_rail_case(8)` / `relic_rail_case(8, "ranged")` -> le dict de mesure du
    montage #357.

    PORTE pytest de `scripts/python/probe_357_relic_rail.py` : `tauFarsight` (ETAT 3, injecte au
    catalogue) equipe de `DawnBlade` au niveau EXACT demande (montage #237), amene au CONTACT d'une
    victime a 1 PV, puis kill REEL. La MEME capture pre-kill est rejouee TROIS fois cote port --
    canal #357 fourni / non fourni / fourni mais niveau lu sur le PASSIF -- et c'est le CONTRASTE
    des trois contre le delta de PV NATIF qui prouve quelque chose : la lecture nominale seule
    serait un vert que ni l'absence de rail ni un mauvais palier ne feraient rougir.

    Trois regimes (`probe_357_relic_rail.REGIMES`), dont DEUX negatifs : `melee` (nominal),
    `ranged` (kill a d=2 -> `IsDefeatedByMeleeAttack` refuse) et `fullhp` (porteur a PV pleins ->
    `EntityCanBeRepaired` refuse). Les negatifs verrouillent qu'inscrire la relique n'a pas rendu
    le port PERMISSIF -- l'autre facon de se tromper.

    Portee MODULE (chaque couple niveau/regime = un build + une conduite de positions + un kill).
    ⚠ Montage non installe => ECHEC, jamais skip (#268)."""
    cache: dict = {}

    def _case(level: int = 8, regime: str = "melee") -> dict:
        key = (level, regime)
        if key not in cache:
            # `keep=True` : le runner appartient a `build_runner` (teardown du module).
            r = RELIC.run(rpc, level=level, regime=regime, build_runner=build_runner, keep=True)
            if not r.get("ok"):
                pytest.fail("montage relic-rail NON INSTALLE (niveau %d, regime %s) : %s"
                            % (level, regime, r.get("why")))
            cache[key] = r
        return cache[key]

    return _case


# ── #363 — le canal du seed TERTIAIRE est-il ACTIF PAR DEFAUT ? ──────────────────────────────────

@pytest.fixture(scope="module")
def ability_states_default_case(build_runner, rpc):
    """Fabrique : `ability_states_default_case()` -> le dict de mesure du volet `default` de #363.

    PORTE pytest de `scripts/python/probe_363_ability_states_channel.py::run_default` : les QUATRE
    unites qui equipent une relique DES LE SEED BC (`necroSpyder` NetherRealmCasket, `orksRuntherd`
    SupaCyborkBody, `admecMarshall` / `admecRuststalker` KardiocoreGalvanus) montees d'un coup, deux
    par camp, puis la MEME capture chargee de TROIS facons : canal AUTO (le defaut, #363), canal
    REFUSE (`ability_states=False` -- l'etat d'avant) et canal EXPLICITE (`ability_states=<payload>`,
    la reference #357).

    C'est le CONTRASTE des trois qui prouve : le bras `auto` seul serait un vert que ni un
    debranchement du canal ni une lecture par un autre chemin ne feraient rougir. Deux oracles
    INDEPENDANTS l'encadrent -- le payload `unitAbilityStates` (ce que le NATIF a monte) et
    `data/seed-bc.json` (ce que la CONFIG declare).

    Portee MODULE (un seul build pour tout le fichier).
    ⚠ Montage non installe => ECHEC, jamais skip (#268)."""
    cache: dict = {}

    def _case() -> dict:
        if "r" not in cache:
            # `keep=True` : le runner appartient a `build_runner` (teardown du module).
            # `bind_if_unbound=False` : le probe NE LIE PAS le transport ambiant -- le bras `auto`
            # doit s'appuyer sur celui que `conftest.live_session` a lie, sinon la garde resterait
            # verte meme le harnais debranche (et ne garderait donc rien).
            r = ASD.run_default(rpc, build_runner=build_runner, keep=True, bind_if_unbound=False)
            if not r.get("ok"):
                pytest.fail("montage ability-states-default NON INSTALLE : %s" % r.get("why"))
            cache["r"] = r
        return cache["r"]

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
