"""Damage decomposition DIFF — localise l'ETAGE de divergence off vs live (au lieu de fitter un scalaire
sur le degat final). Cf. memory feedback_damage_decomposition_measure_stage + case-68.

METHODE (mirror du pipeline natif) : `base bout -> GetBaseDamageWithFixedPiercedArmor (pierce/armure) ->
result_bout -> CalculateBaseDamageWithAllModifiers (%-mult + ADDITIF via DamageModifiers.Add) -> crit/block
-> Amount final`. On lit la valeur PAR ETAGE des DEUX cotes et on compare :

- LIVE : `modifier-observe` (deja dans les hooks) capte par bout `{base, pierceA, pierceB, penetration,
  result}` via le hook `GetBaseDamageWithFixedPiercedArmor` (value-dump, fire EN COMBAT). `result` = degat
  du bout APRES percage/armure, AVANT l'additif. Le hook `modsDumps` (CalculateAttackerModifiersForPrediction)
  capte l'additif AGREGE cote attaquant (chemin PREDICTION).
- LIVE final : `Amount` par coup depuis les events UnitDamaged.
- OFFLINE : `rr` du runner = `{base, pierce, armor, per_hit, ...}`.

DIAGNOSTIC : si les `result` de bout MATCHENT off/live mais les `Amount` finaux DIFFERENT d'un ecart
constant -> la divergence est POST-result = etage ADDITIF/%-mult (ex. #68 SmashaEad : additif off 599 vs
live 300). Si les `base`/`pierce` different -> divergence AMONT (arme/percage/armure). L'etage qui differe
est LU, pas devine.

ASCII-only (console cp1252). Usage : arm() puis, apres l'attaque live+offline, decomp_report(...)."""
from __future__ import annotations

from typing import Any


def _ok(r: Any) -> bool:
    return isinstance(r, dict) and r.get("ok")


def arm(rpc) -> dict:
    """Arme + reset modifier-observe (idempotent). A appeler APRES amorce, AVANT l'attaque a diagnostiquer."""
    inst = rpc("modifierObserveInstall", {}, 30)
    rpc("modifierObserveReset", {}, 15)
    return inst if isinstance(inst, dict) else {"raw": inst}


def read_live_decomp(rpc) -> dict:
    """Lit la decomposition LIVE capturee depuis le dernier arm() : per-bout (base/pierce/penetration/result),
    additifs agreges attaquant/defenseur, ET l'attribution PAR-SOURCE (chaque effet -> sa contribution retWords
    via BaseEffect.DamageBonusForAttack/HitsBonusForAttack, chemin combat + prediction). Retourne
    {value_dumps, mods, bonus, fires}."""
    st = rpc("modifierObserveStatus", {}, 30)
    if not isinstance(st, dict):
        return {"error": "modifierObserveStatus KO", "value_dumps": [], "mods": [], "bonus": []}
    vds = st.get("valueDumps") or []
    mods = st.get("modsDumps") or []
    bonus = st.get("bonusDumps") or []
    return {
        "value_dumps": [{"idx": v.get("idx"), "base": (v.get("baseIn") or {}).get("i"),
                         "pierceA": (v.get("pierceA") or {}).get("i"),
                         "pierceB": (v.get("pierceB") or {}).get("i"),
                         "penetration": (v.get("penetration") or {}).get("i"),
                         "result": (v.get("result") or {}).get("i")} for v in vds],
        "mods": [{"side": m.get("side"), "additive": (m.get("additive") or {}).get("i"),
                  "pierce": (m.get("pierce") or {}).get("i"),
                  "penetration": (m.get("penetration") or {}).get("i"),
                  "percentsX1000": m.get("percentsX1000")} for m in mods],
        # Attribution PAR-SOURCE : {tag (dmgBonus/hitsBonus), src (classe d'effet), retWords (struct RETOUR
        # brut s32 @0x0..0x60 = la valeur CONTRIBUEE par cet effet)}. C'est la decompo par EFFET, chemin
        # combat inclus (DamageBonusForAttack fire en combat ET prediction). L'offset de l'additif dans
        # retWords est LU sur un cas connu (ex. SmashaEad) puis fige.
        "bonus": [{"tag": bd.get("tag"), "src": bd.get("srcClass"), "retWords": bd.get("retWords")}
                  for bd in bonus if bd.get("tag") in ("dmgBonus", "hitsBonus")],
        # #68 : resolution des variables d'ability {variableId, level, mult, result}. `mult` = le multiplier
        # REELLEMENT applique par le jeu (100=aucun, 180=normal, 90=rarity ?) -> MESURE combat vs prediction.
        # On ne garde que les resolutions AVEC scaling (mult != 100) pour isoler les vars rarity.
        "var_levels": [{"variableId": v.get("variableId"), "level": v.get("level"), "mult": v.get("mult"),
                        "result": v.get("result")}
                       for v in (st.get("varLevelDumps") or []) if v.get("mult") not in (100, -1)],
        # #68 : HitDamage.GetDamage {min,max,avgFlag,result} = plage per-coup COMBAT (additif folde dedans).
        "hit_dmg": [{"min": h.get("min"), "max": h.get("max"), "avg": h.get("avgFlag"),
                     "result": h.get("result")} for h in (st.get("hitDmgDumps") or [])],
        "fires": st.get("fires"),
    }


def decomp_report(off_rr: dict, live_ph: list, live_decomp: dict) -> dict:
    """Construit le tableau de decomposition off vs live + localise l'etage divergent.
    `off_rr` = resultat runner (base/pierce/per_hit). `live_ph` = Amount final par coup live.
    `live_decomp` = read_live_decomp(). Retourne un dict serialisable + une chaine ASCII `table`."""
    off_ph = (off_rr or {}).get("per_hit") or []
    off_base = (off_rr or {}).get("base")
    off_pierce = (off_rr or {}).get("pierce")
    vds = live_decomp.get("value_dumps") or []
    # Bouts live "result" = degat post-percage AVANT additif. On aligne par ordre (per-bout).
    live_results = [v.get("result") for v in vds if v.get("result") is not None]
    live_bout_base = next((v.get("base") for v in vds), None)
    bonus = live_decomp.get("bonus") or []

    # Ecarts finaux par coup + constance (un ecart CONSTANT sur des rolls differents = additif plat).
    n = min(len(off_ph), len(live_ph))
    final_deltas = [off_ph[i] - live_ph[i] for i in range(n)]
    delta_set = sorted(set(final_deltas))
    const_final_delta = delta_set[0] if len(delta_set) == 1 else None

    stage = None
    if final_deltas and all(d == 0 for d in final_deltas):
        stage = "AUCUNE (off == live bit-exact)"
    elif const_final_delta is not None and const_final_delta != 0:
        stage = ("ADDITIF/%%-mult CONSTANT (ecart FINAL constant %+d sur des rolls differents -> un modif "
                 "PLAT/constant ; PAS un desync de base/pierce/hits qui donnerait un ecart chaotique). "
                 "Voir l'attribution PAR-SOURCE ci-dessous pour l'effet responsable." % const_final_delta)
    elif not final_deltas:
        stage = "INDETERMINE (aucun coup capture des deux cotes)"
    else:
        stage = "AMONT ou MIXTE (ecart final NON constant -> base/pierce/hits/rolls divergent en amont)"

    lines = []
    lines.append("=== DAMAGE DECOMP DIFF (off vs live) ===")
    # NB stages DISTINCTS : off_base = STAT Attack offline (rr.base) ; live_bout_base = base PAR BOUT
    # (input de GetBaseDamageWithFixedPiercedArmor, chemin PREDICTION). NE PAS les egaler naivement.
    lines.append("stat Attack (offline rr.base): %s   |   base par-bout (live, PREDICTION): %s"
                 % (off_base, live_bout_base))
    lines.append("pierce (offline rr.pierce): %s" % (off_pierce,))
    lines.append("per-bout live result (post-percage, AVANT additif, PREDICTION): %s" % (live_results,))
    lines.append("per-hit  off  =%s" % (off_ph,))
    lines.append("per-hit  live =%s" % (live_ph,))
    lines.append("per-hit  delta(off-live)=%s  constant=%s" % (final_deltas, const_final_delta))
    lines.append("additive agrege attaquant (mods, PREDICTION): %s"
                 % ([m.get("additive") for m in (live_decomp.get('mods') or [])
                     if m.get('side') == 'attacker'],))
    # Attribution PAR-SOURCE : extrait l'ADDITIF contribue par chaque effet depuis retWords.
    # Offset MESURE sur SmashaEad (retWords[11]=hasValue, retWords[12]=additif=599 ; 0 pour les effets
    # non-additifs) -> LU, pas devine. Les autres axes (%-mult, pierce, hits) restent en retWords brut.
    per_source_additive = {}
    for bd in bonus:
        if bd.get("tag") != "dmgBonus":
            continue
        rw = bd.get("retWords") or []
        add = (rw[12] if (len(rw) > 12 and rw[11]) else 0)
        if add:
            per_source_additive[bd.get("src") or "?"] = add
    lines.append("--- attribution PAR-SOURCE : additif contribue par effet (dmgBonus retWords[12]) ---")
    lines.append("  additif live par effet: %s" % (per_source_additive or "{aucun}",))
    lines.append("=> ETAGE DIVERGENT: %s" % stage)
    if per_source_additive and const_final_delta:
        lines.append("=> NB: l'additif CONTRIBUE (ci-dessus) peut != l'ecart FINAL (%+d) -> un etage AVAL "
                     "(build HitDamage combat) transforme la contribution. Comparer contribution vs ecart."
                     % const_final_delta)
    return {"stage": stage, "const_final_delta": const_final_delta,
            "off_per_hit": off_ph, "live_per_hit": live_ph, "final_deltas": final_deltas,
            "live_results": live_results, "live_bout_base": live_bout_base, "bonus": bonus,
            "per_source_additive": per_source_additive, "table": "\n".join(lines)}
