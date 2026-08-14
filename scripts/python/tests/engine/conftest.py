"""Fixtures locales a la tranche DECISION (prediction / playbook / utilites).

`hammer_corpse_case` (#17, residu « s8 Hammer ») -- MONTAGE NOMME ET REUTILISABLE du filtre VIVANT des
cibles secondaires de `HammerOfWrath` (1153) sur la face DECISION. Le montage lui-meme (build isole,
geometrie DRIVEE autour de la cible, fabrication d'un vrai CADAVRE hex-adjacent, capture du seam de
decision, evaluation de `make_hammer_wrath_events` + instrument de magnitude auto-verifie) vit dans
`scripts/python/probe_17_hammer_corpse.py` -- la fixture n'en est que la PORTE pytest.

Deux regimes, `probe_17_hammer_corpse.CASES` : `witness` (cadavre ET temoin vivant adjacents) et
`corpse-only` (le cadavre est le SEUL adjacent). Ajouter un cas = ajouter une entree la-bas, pas
dupliquer un montage inline dans un test.

Portee MODULE : chaque regime coute un build + un drive + un kill ; les assertions d'un meme fichier se
partagent la mesure.

`martial_inspiration_case` (#17, residu « s18 MartialInspiration ») -- MONTAGE NOMME du canal
`actorStats` PAR-PAS (`TotalAttacksMade`, +0x20) qui indexe la prediction de MartialInspiration
(1191). Montage dans `scripts/python/probe_17_martial_inspiration.py` ; la fixture n'en est que la
porte pytest.

`active_ability_used_case` (#17, l'autre residu `move`) -- MONTAGE NOMME du gate d'entree du
generateur d'abilities de l'IA (`HasFlag(unit, ActiveAbilityUsed = 2)`). Montage dans
`scripts/python/probe_17_active_ability_used_gate.py`.

`normal_attack_bonus_case` (#308) -- MONTAGE NOMME du `+1` que l'attaque NORMALE ajoute a son utilite
d'ACTION (`ALoki_NormalAttackPlaybook<T>$$CalculateCustomUtility` = `Fix64(1)` contre `Fix64(0)` a la
base). Le montage fabrique la fenetre d'exactement UN point d'utilite ou ce terme, et lui seul, decide
l'action. Montage dans `scripts/python/probe_308_normal_attack_bonus.py`.

`target_trait_ability_case` (#316) -- MONTAGE NOMME des GATES DE TRAIT DE LA CIBLE sur le vecteur
PREDICTION D'ABILITY (`generate_multi_hit_attack_prediction`, per-cible de
`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions`). Un seul couple caster/cible, une seule
variable : la ligne `BC.Units[].Traits` de la cible, qui ouvre tour a tour `BeastSlayer_ExtraDmg`
(+20 % melee vs BigTarget/Vehicle) et `MartialKatah_DmgBonus` (+100 % vs Summon) -- deux magnitudes
DIFFERENTES sur le meme etage. Montage dans
`scripts/python/probe_316_ability_prediction_target_traits.py`.

`triggered_average_form_case` (#350-r3b) -- MONTAGE NOMME des DEUX formes de moyenne de la couche
TRIGGERED (`BaseTriggeredAbility$$MinMaxDamage` au slot 4 = TRONCATURE contre
`$$MinMaxDamageAverage` au slot 1 = demi-vers-le-PAIR). Le montage cherche LUI-MEME le regime qui
DISCRIMINE (`minDmg + maxDmg == 3 mod 4`, le seul ou les deux formes different) et fait passer ce
regime par le foyer du moteur. Montage dans
`scripts/python/probe_350r3b_triggered_average_forms.py` ; la fixture n'en est que la porte pytest.
OFFLINE par LECTURE (aucune des deux formes ne depend de l'etat de bataille), donc pas de
`live_session` : la face demi-vers-le-pair n'a PAS d'oracle live, ce qui est nomme dans le probe.

`rarity_separating_case` (#999-r3) -- MONTAGE NOMME du REGIME SEPARANT de la RARETE, et la fixture
la plus reutilisable de la famille : TOUT gate de rarete (`HasRarity`, `UnitsWithRarity`, et les
cinq effets mythiques qui les portent) doit etre tranche LA, jamais dans le regime par defaut du
harnais. `rl_duel build` impose `targetRarity = 5`, donc sans montage les dix unites rendent `5` et
un port SANS gate est d'accord avec le natif PARTOUT -- un vert y est VIDE. Deux bras :
`rarity_separating_case()` (separant, `orksKillaKan` -> `Rarity.Epic`) et
`rarity_separating_case(rarity=None)` (DEGENERE, le temoin qui etablit que le premier separe).
Montage dans `scripts/python/probe_999r3_regime_separant_rarete.py` ; la fixture n'en est que la
porte pytest, et le probe REFUSE de rendre un bras separant qui ne separe pas.

Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un regime non
atteint est un VERT qui ment -- aucune mesure n'a eu lieu et la suite ne rougit pour personne."""
from __future__ import annotations

import pytest

import probe_17_active_ability_used_gate as AAU
import probe_17_hammer_corpse as HC
import probe_17_martial_inspiration as MI
import probe_308_normal_attack_bonus as NAB
import probe_316_ability_prediction_target_traits as TTA
import probe_350r3b_triggered_average_forms as TAF
import probe_999r3_regime_separant_rarete as RAR


@pytest.fixture(scope="module")
def hammer_corpse_case(live_session):
    """Fabrique : `hammer_corpse_case("witness")` -> le dict de mesure du probe #17.

    `live_session` est tire ICI (le montage exige la session Frida) ; le runner est DISPOSE par le probe
    en sortie de `run()`, donc rien a liberer au teardown."""
    cache: dict = {}

    def _case(case: str, seed: int = 17153, board: str = HC.BOARD, center=HC.CENTER) -> dict:
        assert case in HC.CASES, f"cas inconnu : {case} (connus : {sorted(HC.CASES)})"
        key = (case, seed, board, tuple(center))
        if key not in cache:
            r = HC.run(case=case, seed=seed, board=board, center=center, verbose=True)
            if "error" in r:
                pytest.fail(f"montage hammer-corpse NON INSTALLE ({case}, seed={seed}, "
                            f"board={board}, centre={tuple(center)}) : {r['error']}", pytrace=False)
            cache[key] = r
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def martial_inspiration_case(live_session):
    """Fabrique : `martial_inspiration_case()` -> le dict de mesure du probe #17 MartialInspiration.

    Chaque appel monte UN runner isole (build + contact drive + N tours d'attaque) et le DISPOSE en
    sortie de `run()`. Portee MODULE : deux couples (board, seed) = deux mesures, partagees par les
    assertions du fichier."""
    cache: dict = {}

    def _case(seed: int = 11911, board: str = MI.BOARD, rounds: int = 3) -> dict:
        key = (seed, board, rounds)
        if key not in cache:
            r = MI.run(seed=seed, board=board, rounds=rounds, verbose=True)
            if "error" in r:
                pytest.fail(f"montage martial-inspiration NON INSTALLE (seed={seed}, board={board}, "
                            f"rounds={rounds}) : {r['error']}", pytrace=False)
            cache[key] = r
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def active_ability_used_case(live_session):
    """Fabrique : `active_ability_used_case()` -> le dict de mesure du probe #17 gate d'action.

    Chaque appel monte UN runner isole (build + drive au contact + cast d'ItItches) et le DISPOSE en
    sortie de `run()`."""
    cache: dict = {}

    def _case(seed: int = 12100, board: str = AAU.BOARD) -> dict:
        key = (seed, board)
        if key not in cache:
            r = AAU.run(seed=seed, board=board, verbose=True)
            if "error" in r:
                pytest.fail(f"montage active-ability-used NON INSTALLE (seed={seed}, "
                            f"board={board}) : {r['error']}", pytrace=False)
            cache[key] = r
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def normal_attack_bonus_case(live_session):
    """Fabrique : `normal_attack_bonus_case()` -> le dict de mesure du probe #308.

    Chaque appel monte les DEUX bras de l'A/B (`Damage` juste sous / juste au-dessus du seuil de
    bascule natif), pose la geometrie (cible amenee au contact) et DISPOSE ses runners. Les
    `damages` par defaut sont les constantes MESUREES du probe ; en passer d'autres (ou
    `auto=True`) re-calibre le montage sur un autre couple (board, seed, cible).

    Portee MODULE : chaque couple = deux builds, partages par les assertions du fichier."""
    cache: dict = {}

    def _case(board: str = NAB.BOARD, seed: int = NAB.SEED, target: str = NAB.TARGET,
              damages=None, auto: bool = False) -> dict:
        ds = tuple(damages) if damages else (NAB.D_BELOW, NAB.D_WINDOW)
        key = (board, seed, target, ds, auto)
        if key not in cache:
            res = None
            try:
                res = NAB.scenario(board=board, seed=seed, target=target,
                                   damages=None if auto else list(ds), auto=auto, verbose=True)
            except RuntimeError as exc:                 # montage non installe -> ROUGE, jamais skip
                pytest.fail(f"montage normal-attack-bonus NON INSTALLE (board={board}, seed={seed}, "
                            f"cible={target}, damages={ds}) : {exc}", pytrace=False)
            finally:
                if res is not None:
                    NAB.dispose(res)
            cache[key] = res
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def triggered_average_form_case():
    """Fabrique : `triggered_average_form_case(<symbole du call-site natif>)` -> le dict de mesure
    du probe #350-r3b (forme lue, slot invoque, regime discriminant, valeur du foyer, et les DEUX
    formes en regard).

    `level`/`mult` omis -> le PREMIER regime DISCRIMINANT de l'ability (`mn + mx == 3 mod 4`).
    C'est le seul regime qui conclut : partout ailleurs les deux formes coincident et la garde ne
    mesurerait rien. Un call-site sans ability chiffrable ou sans regime discriminant fait ROUGIR
    (`RuntimeError` -> `pytest.fail`), il ne skippe pas.

    Portee MODULE et cache : le montage est offline et pur, les assertions du fichier se partagent
    la mesure."""
    cache: dict = {}

    def _case(call_site: str, level: int | None = None, mult: int | None = None,
              ability_id: str | None = None) -> dict:
        key = (call_site, level, mult, ability_id)
        if key not in cache:
            try:
                cache[key] = TAF.run(call_site, level=level, mult=mult, ability_id=ability_id)
            except RuntimeError as exc:                 # montage non installe -> ROUGE, jamais skip
                pytest.fail("montage triggered-average-form NON INSTALLE (call_site=%s, level=%s, "
                            "mult=%s) : %s" % (call_site, level, mult, exc), pytrace=False)
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def rarity_separating_case(live_session):
    """Fabrique : `rarity_separating_case()` -> le dict de mesure du bras SEPARANT (#999-r3) ;
    `rarity_separating_case(rarity=None)` -> le bras DEGENERE (temoin).

    Cles rendues : `rarityEnum` (nom PLEIN publie par le capteur, a ASSERTIONNER -- cinq enums du
    build partagent les six memes ordinaux), `by_entity` / `by_visual` (ce que le CAPTEUR publie),
    `ctx_by_entity` / `ctxDistinct` (ce que le PORT en fait apres `load_state`, donc la TRAVERSEE),
    `distinct`, `separating`.

    Un bras SEPARANT qui ne separe pas fait ROUGIR (le probe leve, la fixture `fail`) : c'est la
    seule protection contre le vert VIDE que le regime par defaut du harnais fabrique tout seul.

    Chaque appel monte UN runner isole et le DISPOSE en sortie de `run()`. Portee MODULE : les
    assertions d'un meme fichier se partagent la mesure."""
    cache: dict = {}

    def _case(rarity: "int | None" = RAR.RARETE_SEPARANTE, vis: str = RAR.VIS_SEPARE,
              seed: int = RAR.SEED, board: str = RAR.BOARD) -> dict:
        key = (rarity, vis, seed, board)
        if key not in cache:
            try:
                cache[key] = RAR.run(rarity=rarity, vis=vis, seed=seed, board=board, verbose=True)
            except RuntimeError as exc:             # montage non installe -> ROUGE, jamais skip
                pytest.fail("montage rarity-separating NON INSTALLE (rarity=%s, vis=%s, seed=%s, "
                            "board=%s) : %s" % (rarity, vis, seed, board, exc), pytrace=False)
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def target_trait_ability_case(live_session):
    """Fabrique : `target_trait_ability_case()` -> le dict de mesure du probe #316.

    TROIS volets, tous exposes par la MEME fabrique (`variant=`) :
      * `"synthetic"` (defaut) -- quatre bras sur le meme couple caster/cible, seule la ligne
        `BC.Units[].Traits` de la cible change (`[]`, `BigTarget`, `Vehicle`, `Summon`). C'est le
        volet qui isole le gate, et qui porte DEUX magnitudes distinctes ;
      * `"real"` -- CIBLES REELLES : `Traits` NON patche, autre couple (board, seed). Ferme le doute
        que patcher `Traits` fabriquerait un regime artificiel ;
      * `"additive"` -- AUTRE caster, AUTRE ability, AUTRE canal : `adeptCanoness` /
        `BrazierOfHolyFire` (RANGED) et un gate `ForAddition` (`CondemnorStake_ExtraDmg`) au lieu
        d'un `ForPercentIncrease`. Interdit de conclure que le threading n'aurait ete valide que sur
        le canal `%-list`.

    Chaque appel monte un runner par bras (le build suivant remplace le precedent via le meme
    `--state-file`) et DISPOSE ses runners. Portee MODULE : les assertions du fichier se partagent
    la mesure."""
    cache: dict = {}
    # Chaque volet a SON couple (board, seed) par defaut, et ce n'est pas un detail : ils doivent
    # differer, sinon la generalisation geometrique n'est pas exercee.
    defaults = {"synthetic": (TTA.BOARD, TTA.SEED), "real": ("C3_01", 777),
                "additive": ("C4_09", 909)}

    def _case(board: str = None, seed: int = None, target: str = TTA.TARGET,
              variant: str = "synthetic") -> dict:
        assert variant in defaults, f"volet inconnu : {variant} (connus : {sorted(defaults)})"
        d_board, d_seed = defaults[variant]
        board = board if board is not None else d_board
        seed = seed if seed is not None else d_seed
        key = (board, seed, target, variant)
        if key not in cache:
            res = None
            try:
                if variant == "real":
                    res = TTA.scenario_real(board=board, seed=seed, verbose=True)
                elif variant == "additive":
                    res = TTA.scenario_additive(board=board, seed=seed, target=target, verbose=True)
                else:
                    res = TTA.scenario(board=board, seed=seed, target=target, verbose=True)
            except RuntimeError as exc:                 # montage non installe -> ROUGE, jamais skip
                pytest.fail(f"montage target-trait-ability NON INSTALLE (board={board}, seed={seed}, "
                            f"cible={target}, volet={variant}) : {exc}", pytrace=False)
            finally:
                if res is not None:
                    TTA.dispose(res)
            cache[key] = res
        return cache[key]
    return _case
