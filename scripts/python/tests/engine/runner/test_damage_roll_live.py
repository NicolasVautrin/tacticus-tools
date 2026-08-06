"""Tranche DAMAGE, PALIER 1 (mono-coup) — `HitDamage.GetDamage` bit-exact vs LIVE.

On applique une VRAIE attaque normale mono-coup propre (pas de crit/block/bouclier,
1 coup) sur le runner live, encadrée par `dumpRng` (état MT avant/après), et on
REPRODUIT le tirage de dégât avec le MT Python porté.

Pourquoi c'est bit-exact et SANS hypothèse cachée :
  • Ordre RNG RE'd (operations/damage.py) : `HitDamage.GetDamage` est le PREMIER
    consommateur de RNG d'une attaque mono-coup (crit/block viennent APRÈS). Donc le
    1er tirage depuis l'état-AVANT EST le tirage de dégât.
  • Tirage = `rng.Next(min, max+1)` = `next_internal(min, max+1)`. L'OFFSET
    `next_internal(lo,hi) − lo` ne dépend QUE de `range = hi − lo` (prouvé pour le
    chemin pow2 ET le rejet Java) → `next_internal(0, range)` consomme les mêmes
    genrand et rend le même offset que le natif.
  • La PLAGE BRUTE du coup (min,max AVANT armure) = `aiPredict.healthDmg` qui est
    PRÉ-armure (`armorBefore=0`, cf. engine/predict.py PARTIE 1) → range = data-driven,
    aucune constante de spread/extra-max hardcodée.
  • La réduction perçage/armure (`get_damage_with_piercing`, RE'd+validée) s'applique
    APRÈS le tirage → on la rejoue sur la valeur tirée. armure==0 ⇒ identité ⇒ exact.

Property-based, indépendant version/seed (le seed ne fait que générer une bataille).
Skip proprement si pas de session / pas de cas mono-coup propre / dumpRng indispo.
"""
from __future__ import annotations

import pytest

from engine.runner.prng import IntBasedMersenneTwister
from engine.services.static_battle_rules import get_damage_with_piercing

_SEEDS = ["777", "31337", "123"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _genrands_to_reach(mt: IntBasedMersenneTwister, target_mt, target_mti, cap=64):
    """Nb de genrand_int32 pour amener `mt` à (target_mt, target_mti) ; None si > cap."""
    if mt.mt == target_mt and mt.mti == target_mti:
        return 0
    for k in range(1, cap + 1):
        mt.genrand_int32()
        if mt.mt == target_mt and mt.mti == target_mti:
            return k
    return None


# Confonds NEUTRALISES AU BUILD (#419-r5). Ce fichier mesure le TIRAGE DE DEGAT nu : il ne
# retient qu'une attaque << propre >> (`PV.sample_is_clean`), donc sans crit ni block. Il
# trouvait cette attaque SANS RIEN DEMANDER tant que le canal crit/block etait globalement
# muet -- les 4 stats `CritChance`/`CritDamage`/`BlockChance`/`BlockDamage` valaient 0 sur
# TOUTE unite, faute d'items equipes a la normalisation. Ce n'etait pas une propriete du
# montage, c'etait un ACCIDENT GLOBAL : le fichier reposait sur un regime degenere sans le
# dire. Une fois le canal ouvert, plus aucun coup n'est propre et les deux tests partaient en
# skip -- 0 passed / 2 skipped, soit precisement le fichier INERTE que le garde #455 refuse.
# On rend donc le regime EXPLICITE, comme le fait deja `NO_NOISE` de
# `test_dakka_dakka_dakka_live.py` : les quatre faces, parce que `--crit`/`--block-player`
# n'epinglent que les p-units et `--crit-target`/`--block-target` que les a-units.
_NO_NOISE = ["--crit", "0,0", "--crit-target", "0,0",
             "--block-target", "0,0", "--block-player", "0,0"]


@pytest.fixture(scope="session")
def damage_roll_case(live_session, rpc, build_runner):
    """Trouve + applique UNE attaque normale mono-coup propre, encadrée par dumpRng.

    Renvoie le 1er cas exploitable (sur quelques seeds) : plage brute (aiPredict
    pré-armure), perçage/armure, dégât réellement infligé, et les dumps MT avant/après.
    """
    import predict_samples as PV  # harnais de validation prédiction (ex-predict_validate)          # lazy : tire rl_collect_batch
    sid = live_session

    for seed in _SEEDS:
        b = build_runner(seed, extra=_NO_NOISE)
        rid, my_team = b["rid"], b["my_team"]

        probe = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(probe):
            pytest.skip(f"dumpRng indispo (rebuild+reinject hooks ?): {str(probe)[:160]}")

        rows = PV.build_samples(sid, rid, my_team, max_turns=6)
        if not rows:
            continue
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 3, "allAbilities": True}, 90)
        cur = dv.get("currentPlayer")
        u_by_id = {u["id"]: u for u in (dv.get("units") or [])}

        for r in rows:
            # mono-coup, prédiction non-optimiste (cible sans réduction-trigger), et SURTOUT
            # AUCUN ×modifier post-tirage (`r["mods"]`) : ainsi la plage aiPredict (pré-armure,
            # effets pré-tirage déjà inclus) == la plage du tirage HitDamage. Les effets
            # pré-tirage (ex. ExtraDmg) sont OK (cuits dans la plage) ; seuls les ×bonus
            # post-perçage (§17.7) la décaleraient.
            if r["hits"] != 1 or not PV.sample_is_clean(r) or r["mods"]:
                continue
            att = u_by_id.get(r["att"]); tgt = u_by_id.get(r["tgt"])
            if not att or not tgt or not att.get("alive") or not tgt.get("alive"):
                continue
            if att.get("owner") != cur:                 # doit être à mon tour pour agir
                continue
            norm = next((ab for ab in (att.get("abilities") or [])
                         if ab.get("kind") == "normal"), None)
            if not norm:
                continue

            # aiPredict (PRÉ-armure) : plage brute + flags + état cible, depuis la tile COURANTE.
            ap = rpc("aiPredict", {"runnerId": rid, "unitId": r["att"],
                                   "targetId": r["tgt"], "abilityType": norm["id"]}, 60)
            if not _ok(ap):
                continue
            pred = ap.get("pred")
            if not pred or ap.get("dictNull"):
                continue
            if pred.get("appliedHits") != 1 or pred.get("mightCrit"):
                continue                                 # mono-coup, pas de crit
            if pred.get("shieldBefore"):
                continue                                 # pas de bouclier (delta santé = dégât)
            raw_min = int(pred.get("healthDmgMin") or 0)
            raw_max = int(pred.get("healthDmgMax") or 0)
            if raw_max <= raw_min:
                continue                                 # spread nul → 0 tirage : non pertinent
            hp_before = int(pred.get("hpBefore") or 0)
            if hp_before <= 0:
                continue

            s1 = rpc("dumpRng", {"runnerId": rid}, 30)
            if not _ok(s1):
                continue
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": r["att"], "targetId": r["tgt"],
                "abilityType": norm["id"]}}, 40)
            s2 = rpc("dumpRng", {"runnerId": rid}, 30)
            if not (_ok(res) and _ok(s2)):
                continue
            ar = (res.get("actions") or [{}])[0]
            if not ar.get("ok"):
                continue                                 # cast invalide (hors portée) → unité suivante
            hp_after = next((u.get("hp") for u in (res.get("units") or [])
                             if u.get("squadId") == r["tgt"]), None)
            if hp_after is None:
                continue
            actual = hp_before - int(hp_after)
            if actual <= 0:                              # rien infligé (no-op) → suivant
                continue

            return {
                "seed": seed, "att": r["att"], "tgt": r["tgt"],
                "raw_min": raw_min, "raw_max": raw_max,
                "pierce": int(r["pierce"]), "armor": int(r["armor"]),
                "hp_before": hp_before, "actual": actual,
                "s1": s1, "s2": s2,
            }

    pytest.skip("aucune attaque normale mono-coup propre applicable depuis la tile "
                "courante (hits==1, sans crit/bouclier/effet, dégât>0) sur les seeds testés")


def test_single_hit_roll_reproduces_actual_damage(damage_roll_case):
    """CŒUR PALIER 1 : le MT Python, parti de l'état-AVANT, reproduit le tirage de
    dégât du coup → dégât prédit == dégât réellement infligé (bit-exact si armure==0).

      roll      = raw_min + next_internal(0, raw_max−raw_min+1)   # offset depuis le RNG live
      predicted = get_damage_with_piercing(roll, pierce, armor)   # réduction RE'd (après tirage)
    """
    c = damage_roll_case
    rng_range = c["raw_max"] - c["raw_min"] + 1
    mt = IntBasedMersenneTwister()
    mt.mt = list(c["s1"]["mt"]); mt.mti = c["s1"]["mti"]
    offset = mt.next_internal(0, rng_range)              # dépend du range seul = offset natif
    roll = c["raw_min"] + offset
    predicted = get_damage_with_piercing(roll, c["pierce"], c["armor"])
    print(f"\n[DAMAGE p1] seed {c['seed']} u{c['att']}→u{c['tgt']} : raw {c['raw_min']}..{c['raw_max']} "
          f"range={rng_range} offset={offset} → roll={roll} | pierce={c['pierce']} armor={c['armor']} "
          f"→ predicted={predicted} vs live actual={c['actual']} (Δ={predicted - c['actual']})")
    tol = 0 if c["armor"] == 0 else 1                    # armure==0 → exact ; sinon ±1 (arrondi Fix64)
    assert abs(predicted - c["actual"]) <= tol, (
        f"tirage de dégât NON reproduit : roll={roll} (raw {c['raw_min']}..{c['raw_max']}, "
        f"offset={offset}), pierce={c['pierce']} armor={c['armor']} → predicted={predicted}, "
        f"live actual={c['actual']} (seed {c['seed']}, u{c['att']}→u{c['tgt']})")


def test_single_hit_consumes_the_damage_roll(damage_roll_case):
    """STRUCTUREL : l'attaque a fait AVANCER le RNG (≥1 genrand) d'un nombre BORNÉ —
    le tirage de dégât a bien consommé du MT, sans cascade RNG géante (cas propre)."""
    c = damage_roll_case
    mt = IntBasedMersenneTwister()
    mt.mt = list(c["s1"]["mt"]); mt.mti = c["s1"]["mti"]
    k = _genrands_to_reach(mt, list(c["s2"]["mt"]), c["s2"]["mti"], cap=64)
    assert k is not None, "l'état MT après l'attaque n'est pas atteignable en ≤64 genrand"
    assert k >= 1, "une attaque à spread non nul doit consommer ≥1 tirage de dégât"
    assert k <= 8, f"trop de genrand consommés ({k}) pour un coup propre — cascade RNG inattendue"
