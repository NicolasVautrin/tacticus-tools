"""#237-r1 OFFLINE -- `rl_duel build --equip-relic` INJECTE son porteur au catalogue.

L'ETAT 3 de la gate de confrontabilite d'une relique (« porteur HORS pool ») exigeait DEUX
commandes -- `catalog_inject.write_relic_seed_bc` puis `build --seed-bc` -- et rien ne le disait :
`--equip-relic adeptCelestine:TheArdentBlade:1` sortait en `rc 2` sur
`'adeptCelestine' absent de BC.Units -- injecter d'abord le porteur (write_augmented_seed_bc)`,
alors que le `--equip-mythic` VOISIN augmentait le catalogue tout seul. La cause etait
structurelle, pas un oubli : `equip_relic` court APRES `_normalize_and_extract_pool` (le niveau
EXACT l'exige -- `buildNormalizedBC` reecrit `TertiaryAbilityLevel = 50` des que `TertiaryAbility`
est non nul), donc un porteur absent du seed BC n'etait dans AUCUN des deux BC.

Ce fichier garde les deux faces du correctif, et le PERIMETRE de son regime :
  1. l'etat 3 a DISPARU de l'entree partagee -- epingle dans les deux sens -- et le regime est
     desormais FABRIQUE (un seed BC custom d'ou les porteurs d'une relique ont ete retires) ;
  2. dans ce regime, le seed BC vu par la normalisation porte le greffon, et la relique est posee ;
  3. HORS regime (porteur deja au catalogue), le seed BC est IDENTIQUE a celui d'un build sans
     relique -- aucune augmentation parasite ;
  4. contre-epreuve par MUTATION : `augment` neutralise fait retomber l'etage 2 en `rc 2`.

⚠ L'ETAT 3 NE SE RENCONTRE PLUS TOUT SEUL (#10039). `data/seed-bc.json` n'est plus la capture
d'UNE bataille (ou 9 porteurs de relique manquaient) mais un catalogue FORGE par
`Idun.Source.IdunBattle.View.BattleConfigBuilder`, qui porte les 127 `lineup` :
`_reliques_hors_seed()` rend `{}`. La garde de non-vacuite de l'etage 1 a donc fait exactement ce
pour quoi elle etait ecrite -- ROUGIR au lieu de laisser les trois etages suivants s'executer sur
un ensemble vide. Le correctif, lui, garde tout son objet : un seed BC custom peut ecarter un
porteur, et c'est ce regime-la qu'on construit. Un etage qui attend qu'un accident de donnee lui
fournisse son cas cesse de mordre le jour ou la donnee change.

Tout est offline : `_normalize_and_extract_pool` (le seul appel RPC du chemin) est substitue, et
c'est LUI qui capture le seed BC -- la position exacte ou la question se pose.
"""
from __future__ import annotations

#: Perimetre : le montage tertiaire de `rl_duel` (le foyer du correctif), les primitives de
#: catalogue qu'il enchaine, et les DEUX entrees dont la premisse se derive -- le seed BC (qui dit
#: quels porteurs manquent) et le gameconfig (qui dit quels porteurs une relique admet).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
        "data/seed-bc.json",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : garde que `--equip-relic` injecte son porteur au catalogue AVANT la "
              "normalisation (#237-r1), que le montage reste un NO-OP quand le porteur est deja "
              "la, et que le diagnostic distingue 'absent du catalogue' de 'ecarte par "
              "buildNormalizedBC'. La premisse (des reliques dont aucun porteur n'est au seed BC) "
              "est DERIVEE du gameconfig et du seed BC, jamais citee -- un build qui les ferait "
              "entrer au seed doit faire ROUGIR le fichier, pas le rendre vacant.",
}

import copy          # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
import json          # noqa: E402
import sys           # noqa: E402
from pathlib import Path                                                      # noqa: E402

import pytest        # noqa: E402

_SP = Path(__file__).resolve().parents[2]
if str(_SP) not in sys.path:
    sys.path.insert(0, str(_SP))

import catalog_inject as C                                                    # noqa: E402
import rl_duel                                                                # noqa: E402

_SEED = _SP.parents[1] / "data" / "seed-bc.json"


def _seed_ids() -> set:
    bc = json.loads(_SEED.read_text(encoding="utf-8"))
    return {u.get("Id") for u in (bc.get("Units") or [])}


def _porteurs_par_ability() -> dict:
    par_ability: dict = {}
    for meta in C.relic_items().values():
        par_ability.setdefault(meta["ability"], set()).update(meta["allowedUnits"])
    return par_ability


def _reliques_hors_seed(ids: set | None = None) -> dict:
    """{ability: [porteurs]} des reliques dont AUCUN porteur n'est au catalogue (ETAT 3)."""
    ids = _seed_ids() if ids is None else ids
    return {a: sorted(p) for a, p in _porteurs_par_ability().items() if not (p & ids)}


def _reliques_au_seed() -> dict:
    """{ability: [porteurs au catalogue]} -- le regime MAJORITAIRE (etats 1 et 2), ou le correctif
    doit etre un NO-OP EXACT."""
    ids = _seed_ids()
    return {a: sorted(p & ids) for a, p in _porteurs_par_ability().items() if (p & ids)}


def _regime_etat3(tmp_path) -> tuple:
    """FABRIQUE l'ETAT 3 au lieu de l'attendre : un seed BC d'ou TOUS les porteurs d'une relique
    ont ete retires. Rend `(chemin, unitId, ability)`.

    ⚠ POURQUOI FABRIQUER (#10039). L'etat 3 se rencontrait TOUT SEUL tant que `data/seed-bc.json`
    etait la capture d'UNE bataille : 9 porteurs de relique n'y etaient pas. Le catalogue est
    desormais FORGE par `Idun.Source.IdunBattle.View.BattleConfigBuilder` et porte les 127
    `lineup`, donc `_reliques_hors_seed()` rend `{}` -- et les quatre etages qui s'appuyaient
    dessus levaient `IndexError` ou rougissaient sur leur propre premisse.

    Le CORRECTIF, lui, garde toujours son objet : un seed BC custom peut ecarter un porteur (c'est
    ce que fait tout montage filtre), et `--equip-relic` doit alors l'injecter au catalogue AVANT
    la normalisation. On construit donc le regime, exactement comme #380 construit sa derive et
    comme `test_le_rattrapage_repare_...` fabrique la sienne : un etage qui attend qu'un accident
    de donnee lui fournisse son cas cesse de mordre le jour ou la donnee change.
    """
    bc = json.loads(_SEED.read_text(encoding="utf-8"))
    ids = {u.get("Id") for u in (bc.get("Units") or [])}
    porte = {u["Id"] for u in (bc.get("Units") or []) if u.get("TertiaryAbility")}
    cand = sorted((a, sorted(p)) for a, p in _porteurs_par_ability().items()
                  if p and p <= ids and not (p & porte))
    assert cand, ("aucune relique dont TOUS les porteurs sont au catalogue et sans relique "
                  "equipee -- le regime n'est plus fabricable, re-mesurer #237-r1")
    ability, porteurs = cand[0]
    bc["Units"] = [u for u in bc["Units"] if u.get("Id") not in set(porteurs)]
    # ... et la config d'ability part avec eux : c'est l'etat 3 COMPLET (le porteur ET sa config
    # manquent), celui que `--equip-relic` doit reconstituer.
    for node in ("PassiveAbilities", "ActiveAbilities"):
        (bc.get("Abilities") or {}).get(node, {}).pop(ability, None)
    p = tmp_path / "seed-bc-etat3.json"
    p.write_text(json.dumps(bc), encoding="utf-8")
    C.write_pins(p, [], withheld=["PassiveAbilities/" + ability])   # #380 : le chargeur la reposerait
    return p, porteurs[0], ability


class _Capture:
    """Substitut de `_normalize_and_extract_pool` : capture le seed BC RECU et rend un BC normalise
    qui en derive. C'est la position exacte du correctif -- ce que la normalisation voit."""

    def __init__(self):
        self.seed_bc = None

    def __call__(self, sid, seed_bc, rank, **kw):
        self.seed_bc = copy.deepcopy(seed_bc)
        template = copy.deepcopy(seed_bc)
        pool = sorted({u.get("Id") for u in (template.get("Units") or []) if u.get("Id")})
        return template, pool, []


def _build(monkeypatch, argv: list) -> tuple:
    """Joue `rl_duel.main(['build', '--list-pool', ...])` SANS session. Rend `(rc, capture)`.

    `--list-pool` sort juste APRES les montages tertiaires et AVANT tout RPC de build : c'est le
    seul point d'arret qui traverse le correctif sans monter de runner.
    """
    cap = _Capture()
    monkeypatch.setattr(rl_duel, "_normalize_and_extract_pool", cap)
    monkeypatch.setattr(rl_duel, "_resolve_session", lambda *a, **k: 1)
    monkeypatch.setattr(rl_duel, "_ensure_ai_trace", lambda *a, **k: None)
    monkeypatch.setattr(rl_duel.runner_state, "current_identity", lambda *a, **k: None)
    rc = rl_duel.main(["build", "--list-pool"] + argv)
    return rc, cap


# ------------------------------------------------------- 1. la PREMISSE, derivee et NON DEGENEREE
def test_premisse_l_etat3_ne_se_rencontre_plus_mais_se_FABRIQUE(tmp_path):
    """L'ETAT 3 a DISPARU du catalogue partage -- et c'est le fait qu'il faut epingler, pas taire.

    ⚠ CE TEST EXIGEAIT L'INVERSE (#10039). Il assertionnait `_reliques_hors_seed()` NON VIDE, pour
    que le fichier ne devienne pas vacant si tous les porteurs entraient au seed. Ils y sont TOUS
    entres : `data/seed-bc.json` est desormais FORGE par
    `Idun.Source.IdunBattle.View.BattleConfigBuilder`, qui porte les 127 `lineup`. La garde a donc
    fait exactement ce pour quoi elle etait ecrite -- rougir plutot que se vider en silence.

    Le remede n'est pas de la retirer mais de DEPLACER ce qu'elle garde : on epingle la
    disparition (dans les deux sens : si un porteur ressort du catalogue, il faut le savoir), et
    le regime lui-meme est FABRIQUE pour les etages suivants.
    """
    assert _reliques_hors_seed() == {}, (
        "des reliques ont a nouveau TOUS leurs porteurs hors du catalogue : l'ETAT 3 se rouvre "
        "dans l'entree partagee. Ce n'est pas une faute -- mais les etages suivants peuvent alors "
        "s'appuyer dessus au lieu de le fabriquer, et il faut le relire : %r"
        % _reliques_hors_seed())
    # Et le regime MAJORITAIRE existe, sinon l'etage 3 (no-op) ne mesurerait rien.
    assert _reliques_au_seed(), "aucune relique n'a de porteur au catalogue -- etage 3 degenere"
    # ... et le regime FABRIQUE est bien l'etat 3, sur le seed BC qu'on vient d'ecrire.
    p, uid, ability = _regime_etat3(tmp_path)
    ids = {u.get("Id") for u in json.loads(p.read_text(encoding="utf-8"))["Units"]}
    assert uid not in ids
    assert _reliques_hors_seed(ids).get(ability) is not None, (
        "le seed fabrique ne place pas %r en etat 3" % ability)


# --------------------------------------------------- 2. DANS le regime : le greffon est au seed BC
def test_le_porteur_hors_seed_entre_au_catalogue_et_la_relique_est_posee(monkeypatch, tmp_path):
    p, uid, ability = _regime_etat3(tmp_path)
    assert uid not in {u.get("Id") for u in json.loads(p.read_text(encoding="utf-8"))["Units"]}

    rc, cap = _build(monkeypatch, ["--seed-bc", str(p), "--equip-relic", f"{uid}:{ability}:1"])
    assert rc == 0, f"build refuse pour {uid}:{ability}"
    assert cap.seed_bc is not None, "la normalisation n'a jamais ete atteinte"
    vus = {u.get("Id") for u in (cap.seed_bc.get("Units") or [])}
    assert uid in vus, (f"{uid} absent du seed BC vu par buildNormalizedBC -- l'augmentation "
                        f"catalogue de --equip-relic ne mord pas")


def test_le_niveau_exact_survit_a_la_normalisation(monkeypatch, tmp_path):
    """La relique est posee APRES la normalisation, donc au niveau DEMANDE (et non 50).

    C'est la raison d'etre de l'ordre choisi : `buildNormalizedBC` reecrit
    `TertiaryAbilityLevel = targetAbilityLevel` des que `TertiaryAbility` est non nul.
    """
    p, uid, ability = _regime_etat3(tmp_path)

    # Le substitut rend un template DERIVE du seed : on relit ce que le montage a ecrit dessus en
    # se replacant sur le meme objet que `cmd_build` a patche.
    vus = {}

    class _Cap2(_Capture):
        def __call__(self, sid, seed_bc, rank, **kw):
            t, pool, m = super().__call__(sid, seed_bc, rank, **kw)
            vus["template"] = t
            return t, pool, m

    cap = _Cap2()
    monkeypatch.setattr(rl_duel, "_normalize_and_extract_pool", cap)
    monkeypatch.setattr(rl_duel, "_resolve_session", lambda *a, **k: 1)
    monkeypatch.setattr(rl_duel, "_ensure_ai_trace", lambda *a, **k: None)
    monkeypatch.setattr(rl_duel.runner_state, "current_identity", lambda *a, **k: None)
    rc = rl_duel.main(["build", "--list-pool", "--seed-bc", str(p),
                       "--equip-relic", f"{uid}:{ability}:1"])
    assert rc == 0

    porteur = [u for u in (vus["template"].get("Units") or []) if u.get("Id") == uid]
    assert porteur, f"{uid} absent du BC normalise"
    assert porteur[0].get("TertiaryAbility") == C.triggered_ability_id(ability)
    assert porteur[0].get("TertiaryAbilityLevel") == 1, (
        "le niveau demande n'a pas survecu -- la relique a ete posee AVANT la normalisation")
    cfg = ((vus["template"].get("Abilities") or {}).get("PassiveAbilities") or {})
    assert ability in cfg, ("la config d'ability manque : 11 des 32 reliques sont absentes du "
                            "catalogue -> « system error » au cast")


# ------------------------------------------------------- 3. HORS regime : NO-OP EXACT sur le seed
def test_no_op_exact_quand_le_porteur_est_deja_au_seed(monkeypatch):
    """Un porteur DEJA au catalogue ne declenche AUCUNE augmentation.

    Le temoin est le seed BC d'un build SANS `--equip-relic`, compare octet a octet : c'est la
    seule formulation qui verrait une augmentation parasite (un compte d'unites la manquerait si
    `augment` remplacait une entree au lieu d'en ajouter).
    """
    au_seed = _reliques_au_seed()
    ability, porteurs = sorted(au_seed.items())[0]
    uid = porteurs[0]

    rc_t, cap_t = _build(monkeypatch, [])
    assert rc_t == 0
    rc, cap = _build(monkeypatch, ["--equip-relic", f"{uid}:{ability}:1"])
    assert rc == 0
    assert json.dumps(cap.seed_bc, sort_keys=True) == json.dumps(cap_t.seed_bc, sort_keys=True), (
        f"--equip-relic {uid}:{ability} a modifie le seed BC alors que le porteur y etait deja")


# ------------------------------------------- 4. CONTRE-EPREUVE : le correctif neutralise RETOMBE
def test_mutation_augment_neutralise_fait_retomber_le_regime(monkeypatch, tmp_path):
    """Sans l'augmentation, l'etage 2 redevient `rc 2` -- l'etat mesure AVANT le correctif.

    La mutation porte sur `catalog_inject.augment`, rendu IDENTITE : c'est exactement ce que
    faisait l'absence du bloc, et ca prouve que l'etage 2 mesure le correctif et non le decor.
    """
    p, uid, ability = _regime_etat3(tmp_path)
    monkeypatch.setattr(C, "augment", lambda bc, ids, rank=17, ability_level=50: (bc, [], [], []))
    rc, _cap = _build(monkeypatch, ["--seed-bc", str(p), "--equip-relic", f"{uid}:{ability}:1"])
    assert rc == 2, ("augment neutralise et le build passe quand meme : l'etage 2 ne mesure pas "
                     "le correctif")


# ------------------------------------ 5. le DIAGNOSTIC distingue les deux causes d'un porteur absent
def test_diag_porteur_ecarte_ne_parle_que_dans_son_regime():
    """`_diag_porteur_ecarte` ne s'exprime QUE pour « au seed, ecarte par la normalisation ».

    Les trois autres positions (absent partout / present partout / present seulement au normalise)
    doivent rendre la chaine VIDE : un diagnostic qui parle a tort est pire que pas de diagnostic.
    """
    seed = {"Units": [{"Id": "x"}]}
    norm = {"Units": [{"Id": "x"}]}
    vide = {"Units": []}
    assert rl_duel._diag_porteur_ecarte("x", seed, vide), "regime cible muet"
    assert "buildNormalizedBC" in rl_duel._diag_porteur_ecarte("x", seed, vide)
    assert rl_duel._diag_porteur_ecarte("x", vide, vide) == ""
    assert rl_duel._diag_porteur_ecarte("x", seed, norm) == ""
    assert rl_duel._diag_porteur_ecarte("x", vide, norm) == ""
