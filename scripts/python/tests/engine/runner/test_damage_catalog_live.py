"""COUVERTURE CATALOGUE — axe DÉGÂT : valide l'attaque normale de CHAQUE unité (data-driven
`unit_map`) par replay-diff bit-exact vs live. 1ʳᵉ brique du programme « valider chaque
playbook/ability/effet/trait via test ».

Périmètre v1 = unités **vanilla melee-multihit** (arme mêlée ≥2 coups, AUCUN modificateur de
dégât d'ability/trait : `unit_map._has_dmg_mod` faux) → l'attaque normale doit être reproduite
À L'UNITÉ par le moteur de dégât porté (spread→perçage/armure→multi-coups). Un MISMATCH ici =
vrai trou du moteur sur ce profil d'arme/trait (le but : le SURFACER).

**GATE DE CONFRONTABILITÉ (#462-r4e)** — le catalogue ne s'échantillonne que parmi les porteurs
qui arrivent RÉELLEMENT en bataille par `--p-units`. Sans elle le fichier n'a JAMAIS rien mesuré :
`unit_map.all_kits()` balaie `lineup` + `npc` + `summons`, et la tête alphabétique du profil est
`adeptSmnGeminaeSuperia`, un **SUMMON**. Un summon n'a pas de stats de progression propres
(`Damage`/`Armor`/`Health` absents du gameconfig — il hérite de son summoner), donc
`buildNormalizedBC` le rejette au rank cible : il est dans `BC.Units` du seed mais jamais dans le
pool. Mesuré le 2026-08-03 : les 4 têtes du régime par défaut étaient 1 summon + 3 npc, donc 4
builds refusés (`--p-units: hors pool / non spawnables au rank 17`). Chronologie : 4 skips VERTS
silencieux depuis la création (2026-06-29), convertis en ROUGE par le hook #77 (`build runner KO`
→ échec), inventoriés par #462.

Ce que le catalogue COUVRE / ce qu'il PERD, mesuré (80 unités au profil vanilla melee-multihit) :
  * **9 `lineup`**, dont **6 confrontables** (`admecManipulus` 2h/p30, `astraBullgryn` 4h/p1,
    `astraCreed` 2h/p10, `genesMagus` 2h/p100, `tauAunShi` 5h/p40, `tauDarkstrider` 3h/p1) ;
  * **3 `lineup` NON confrontables** : `eldarLhykhis` 5h/p60 et `thousSekhetar` 2h/p40 (absents du
    seed BC → injection catalogue, `catalog_inject.write_augmented_seed_bc` + `build --seed-bc`),
    `necroPlasmancer` 2h/p65 (seul refus légitime — `unspawnable_rank17`, il passe la normalisation
    puis lève au spawn) ;
  * **14 `summons` + 57 `npc` NON couverts par cette voie.** Ce n'est pas « non confrontable » :
    un summon s'observe en spawnant son summoner (#291) et une ability npc se greffe (case-92
    §5bis) — mais ce harnais PILOTE l'attaquant (`applyAction` move + attaque normale), et un
    summon ne se commande pas (son tour est terminé d'office par
    `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`). Le canal qui les couvrirait est un MODE
    DE COUVERTURE SÉPARÉ : replay des events du cast du summoner, comme le fait
    `probe_291_summon_activation.py` — pas `replay_normal_attack`.

CE QUE CE FICHIER NE MESURE PAS — le **régime OVERKILL** (le replay tourne sur UN couple
(board, seed), où la cible survit). Il est porté et gardé AILLEURS depuis `#462-r4e-o` : le natif
n'écrit pas le dégât demandé dans le tag `Amount` mais la somme des retraits RÉELS, bornés aux PV
restants par `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`
(`test_overkill_amount_live.py`, `probe_462_r4e_o_overkill_amount.py`,
`docs/rl/case-462-r4e-o-amount-borne-aux-pv.md`). `_diag_overkill` reste ici avec le sens INVERSE :
s'il s'arme, c'est cette borne qui a régressé — pas un trou du moteur de dégât (#462-r6).

Échelle : par défaut on teste un ÉCHANTILLON (cap `DAMAGE_CATALOG_N`, défaut 4) du catalogue
confrontable ; `DAMAGE_CATALOG_UNITS="a,b,c"` force une liste (dérogation explicite : la gate ne
s'y applique pas) ; `DAMAGE_CATALOG_N=0` = tout le catalogue confrontable (6 unités, 31,6 s
mesurées le 2026-08-03). Cible vanille = eldarFarseer.

Les axes crit/block/effet-crit ont leurs tests dédiés (test_damage_{crit,block}_live) ; les unités
NON-vanilla (ability/effet/trait sur l'attaque) = modes de couverture séparés à venir (résolution
d'ability, mécaniques effet/trait), souvent xfail tant que non portés.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))      # tests/engine/runner → import du helper sibling

from _combat_replay import replay_normal_attack  # noqa: E402

TARGET = "eldarFarseer"          # cible vanille (aucune reduction de degat)
RANK = 17                        # rank par defaut de `rl_duel build` (--rank), celui du pool

# Confonds NEUTRALISES AU BUILD (#419-r6). ARBITRAGE : l'axe de ce catalogue est nomme dans
# l'en-tete -- spread -> percage/armure -> MULTI-COUPS -- et l'en-tete dit deja que « les axes
# crit/block/effet-crit ont leurs tests dedies ». Un coup crite est donc HORS AXE ici, et le
# fichier le traite comme tel : il SKIPPE. Tant que le canal crit/block etait globalement muet il
# n'avait jamais a le faire ; le defaut bascule a « equiper » (#419-r6) rend le crit possible sur
# toute unite, et le fichier tombait a 1 passed + 4 skipped -- des profils d'arme entiers cessaient
# d'etre mesures EN SILENCE, ce qui est exactement le vice que ce fichier a deja porte deux mois.
# On neutralise donc sur les QUATRE faces : `--crit`/`--block-player` n'epinglent que les p-units
# (ici l'attaquant), `--crit-target`/`--block-target` que les a-units (ici la cible).
_NO_NOISE = ["--crit", "0,0", "--crit-target", "0,0",
             "--block-target", "0,0", "--block-player", "0,0"]


def _profile(k):
    """(coups, percage) de l'arme de MELEE la plus multi-coups du kit -- les deux axes que ce
    catalogue mesure."""
    melee = [w for w in k["weapons"] if w["melee"]]
    hits = max((w["hits"] for w in melee), default=0)
    pierce = max((w["pierce"] for w in melee if w["hits"] == hits), default=0)
    return hits, pierce


def _confrontable_ids(kits):
    """Gate de confrontabilite (CLAUDE.md) appliquee AU CHOIX DE L'ECHANTILLON.

    Le pool spawnable est une donnee LIVE (`rl_duel build --list-pool` -> RPC `buildNormalizedBC`),
    indisponible a la COLLECTE : la fixture `live_session` -- donc l'amorce -- n'a pas encore
    tourne, et un RPC IL2CPP avant amorce, c'est le crash 0x2c. On le DERIVE donc des ENTREES
    VERSIONNEES, et `test_derivation_du_pool_fidele` confronte cette derivation au pool REEL a
    chaque passe : sans ce garde la derivation partirait a la derive en silence, ce qui est
    exactement le vice que ce fichier a porte deux mois.

    Trois conditions, chacune fermant une classe de non-spawnable MESUREE le 2026-08-03 :
      * `kind == "lineup"` -- ecarte les 57 npc et 14 summons du profil (cf. en-tete) ;
      * present dans `BC.Units` du seed BC -- le pool en est un sous-ensemble STRICT (97/97) ;
      * hors `unspawnable_rank<RANK>` -- le seul refus legitime du CLAUDE.md.
    """
    import json

    import rl_collect_batch as RCB

    with open(RCB.SEED_BC, encoding="utf-8") as f:
        seed_ids = {u["Id"] for u in (json.load(f).get("Units") or []) if "Id" in u}
    bad_units, _bad_mow = RCB._load_unspawnable(RANK)
    return [k for k in kits
            if k["kind"] == "lineup" and k["id"] in seed_ids and k["id"] not in bad_units]


def _sample(kits, n):
    """UN representant par valeur de coups, du plus petit au plus grand, puis complement.

    L'axe que ce catalogue mesure est nomme dans l'en-tete : spread -> percage/armure ->
    MULTI-COUPS. Le tri alphabetique d'origine n'echantillonnait rien de cet axe (ses 4 premiers
    partageaient 2 valeurs de coups -- et aucun n'etait spawnable). Ici l'echantillon par defaut
    couvre TOUTES les valeurs de coups du catalogue confrontable (2, 3, 4, 5) ; a coups egaux on
    prend le percage le plus ELEVE, seul regime ou l'armure de la cible est annulee, que les
    autres groupes ne portent pas. Deterministe (`id` en dernier critere)."""
    ordered = sorted(kits, key=lambda k: (_profile(k)[0], -_profile(k)[1], k["id"]))
    heads, rest, seen = [], [], set()
    for k in ordered:
        (heads if _profile(k)[0] not in seen else rest).append(k)
        seen.add(_profile(k)[0])
    picked = heads + rest
    return [k["id"] for k in (picked if n <= 0 else picked[:n])]


def _catalog_units():
    """Unites vanilla melee-multihit CONFRONTABLES (data-driven), echantillonnees. Liste calculee
    a la collecte."""
    env = os.environ.get("DAMAGE_CATALOG_UNITS")
    if env:
        return [u.strip() for u in env.split(",") if u.strip()]
    try:
        import unit_map as UM
    except Exception:
        return []
    cands = [k for k in UM.all_kits()
             if k["id"] != TARGET
             and any(w["melee"] and w["hits"] >= 2 for w in k["weapons"])
             and not UM._has_dmg_mod(k)]
    return _sample(_confrontable_ids(cands), int(os.environ.get("DAMAGE_CATALOG_N", "4")))


_UNITS = _catalog_units()


def _live_pool(rank=RANK):
    """Pool spawnable REEL au `rank` -- `rl_duel build --list-pool`, parse. Source de verite de
    la gate de confrontabilite (le RPC `buildNormalizedBC` derriere est LIVE, d'ou le subprocess
    plutot qu'un import)."""
    pydir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--list-pool", "--rank", str(rank)],
                       cwd=pydir, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    pool, seen_header = set(), False
    for line in (p.stdout or "").splitlines():
        if line.startswith("[pool]"):
            seen_header = True
            continue
        s = line.strip()
        if seen_header and s and " " not in s:
            pool.add(s)
    if not pool:
        # ROUGE, jamais un skip : sans pool REEL la gate n'est plus gardee, et une gate non
        # gardee est precisement ce qui a laisse ce fichier ne rien mesurer pendant deux mois.
        pytest.fail(f"`rl_duel build --list-pool --rank {rank}` n'a rendu AUCUNE unite -- le pool "
                    "spawnable REEL est indisponible, la gate de confrontabilite ne peut pas etre "
                    f"confrontee (rc={p.returncode}). "
                    f"stdout={(p.stdout or '')[-300:]!r} stderr={(p.stderr or '')[-300:]!r}",
                    pytrace=False)
    return pool


def _diag_overkill(r):
    """Distingue le REGIME OVERKILL d'un vrai trou de calcul, dans le message d'echec.

    La borne est PORTEE depuis #462-r4e-o : le natif n'ecrit pas le degat demande dans le tag
    `Amount` mais la somme des retraits REELS (`FillUpStatComponent$$Reduce` +
    `ApplyDamageOperation$$ReduceShield`, lus depuis le champ @+0 du retour d'
    `ApplyDamageOperation$$Execute`). Ce diagnostic reste, avec le sens INVERSE : s'il s'arme
    desormais, ce n'est plus un ecart connu, c'est la BORNE qui a REGRESSE -- et le message doit
    envoyer vers ses gardes plutot que laisser lire un trou du moteur de degat (#462-r6)."""
    if r.get("live_after") != 0 or r.get("off_after") != 0:
        return ""
    if sum(r["off_ph"]) <= sum(r["live_ph"]):
        return ""
    return (" || REGIME OVERKILL : la cible meurt pendant la salve, l'ETAT est identique "
            f"(hp_after 0 = 0) et seules les sommes rapportees different "
            f"(live={sum(r['live_ph'])} = PV de la cible, off={sum(r['off_ph'])}). Le natif borne "
            "`Amount` aux PV restants -- BORNE PORTEE par #462-r4e-o, donc ceci est une REGRESSION "
            "de `damage_amount_applied` (damage_hits.py), PAS un trou du moteur de degat. Gardes : "
            "`test_overkill_amount_live.py`, `probe_462_r4e_o_overkill_amount.py` ; RE : "
            "docs/rl/case-462-r4e-o-amount-borne-aux-pv.md.")


@pytest.mark.skipif(not _UNITS, reason="unit_map indisponible / aucune unite vanilla melee-multihit")
@pytest.mark.parametrize("attacker", _UNITS)
def test_normal_attack_bit_exact(attacker, live_session, rpc, build_runner):
    """L'attaque normale de `attacker` (vanilla melee-multihit) est reproduite bit-exact offline."""
    r = replay_normal_attack(rpc, build_runner, attacker, target=TARGET, extra=_NO_NOISE)
    if not r["ok"]:
        pytest.skip(f"{attacker}: {r['reason']}")
    if r["did_crit"] or r["did_block"] or r["did_evade"]:
        pytest.skip(f"{attacker}: coup non propre (crit/block/evade live) — hors axe vanilla")
    print(f"\n[CATALOG dmg] {attacker}: hits={r['hits']} live={r['live_ph']} off={r['off_ph']} "
          f"live_after={r['live_after']} off_after={r['off_after']} eff={r['effects']}")
    assert r["exact"], (f"{attacker}: dégât offline != live — per-hit off={r['off_ph']} "
                        f"live={r['live_ph']} (off_after={r['off_after']} live_after={r['live_after']})"
                        + _diag_overkill(r))


def test_derivation_du_pool_fidele(live_session):
    """La gate de confrontabilite DERIVEE (`_confrontable_ids`, offline) rend EXACTEMENT ce que le
    pool LIVE rend sur le meme profil -- et la cible du catalogue y est.

    C'est le garde de fidelite de la derivation, et il est la raison pour laquelle celle-ci a le
    droit d'etre offline. Sans lui, une derivation devenue TROP PERMISSIVE se rattraperait en
    `build runner KO` (le rouge de MONTAGE d'origine, qui ressemble trait pour trait a un rouge de
    port -- #462-r6) et une derivation devenue TROP STRICTE laisserait tomber des profils d'arme
    EN SILENCE. Un garde-fou dont le verdict derive ne vaut rien."""
    import unit_map as UM
    cands = [k for k in UM.all_kits()
             if k["id"] != TARGET
             and any(w["melee"] and w["hits"] >= 2 for w in k["weapons"])
             and not UM._has_dmg_mod(k)]
    derive = {k["id"] for k in _confrontable_ids(cands)}
    pool = _live_pool()
    reel = {k["id"] for k in cands if k["id"] in pool}
    assert TARGET in pool, f"cible du catalogue {TARGET} hors pool spawnable rank {RANK}"
    assert derive == reel, (
        f"la gate DERIVEE diverge du pool LIVE (rank {RANK}) -- MONTAGE, pas port. "
        f"derives et hors pool (le build echouerait): {sorted(derive - reel)} ; "
        f"au pool et non derives (profils perdus en silence): {sorted(reel - derive)}")
    if not os.environ.get("DAMAGE_CATALOG_UNITS"):
        assert set(_UNITS) <= pool, (
            f"echantillon non spawnable au rank {RANK}: {sorted(set(_UNITS) - pool)}")
