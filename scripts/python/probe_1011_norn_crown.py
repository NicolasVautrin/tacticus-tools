#!/usr/bin/env python
"""Probe #1011 -- `NornCrown` (relique de `tyranNeurothrope`) MESUREE au natif, par A/B de relique.

LA QUESTION BINAIRE. `IdunBattle.Entities.Effects.Loki.NornCrownEffect$$CreateEffectDamageBonus-
ForAttack` = `ForAddition(get_OwnerIsCaster & HasEffect(Target@+0x60, 0x4c2 = Neuroparasite,
onlyActive: false, 6 = Both), ConfigVar(0x8 = extraDmg, GetAbilityState(effect)))`, et son
`$$CreateTargetSelector` = `Filter(AllUnits@+0x20, AreFriends(Owner@+0x30, It@+0x68, ByCurrentTeam,
false) & IsInTeamSynapseRange(It@+0x68, Owner@+0x30) & (HasTrait(It, Psyker) | HasTrait(It,
Summon)))`. DEUX choses en decoulent, et une seule est ecrite dans l'i2 :

  (a) un ALLIE `Psyker`/`Summon` dans la bulle Synapse gagne `+extraDmg` contre une cible
      Neuroparasitee -- c'est le << Other friendly Psykers ... >> de l'i2 ;
  (b) le PORTEUR lui-meme est dans son propre selecteur, parce que
      `IdunBattle.Core.Services.BattleQuery$$AreFriends` -> `UnitExtensions$$IsFriend` N'ECARTE PAS
      l'egalite. L'i2 dit << Other >> ; le decompile ne l'ecrit pas. **C'est (b) que ce probe
      tranche**, et le verdict decide si la classe d'effet garde sa patte SELF.

LE MONTAGE -- deux runners IDENTIQUES a la RELIQUE PRES (A/B), meme seed, meme board, memes tuiles
explicites (`--place` / `--a-place`), donc l'ecart mesure `NornCrown` et RIEN d'autre :

    (3,2) tyranNeurothrope  -- Psyker ET Synapse, porteur de la relique cote A
    (3,3) astraPrimarisPsy  -- Psyker, a 1 hex du porteur (bulle Synapse = 2) et a 1 hex de la cible
    (3,4) orksNob           -- la cible ; c'est elle qui recevra le Neuroparasite
    (0,5) orksRuntherd      -- ecarte (4 hexes), TEMOIN hors mesure

Sequence par runner : `aiPredict` AVANT parasite, puis attaque normale PSYCHIQUE du Neurothrope sur
`orksNob` (`NeuroparasiteAbility$$CreateTrigger` = `On(9 Attack) & get_OwnerIsCaster & NOT
HasEffect(Target, 0x4c2) & IsUnit(Target) & CurrentAttackDamageProfilesContain(0xd Psychic)`), puis
`aiPredict` APRES.

CE QUE CHAQUE ECART ISOLE :
  * `psyker APRES(A) - psyker APRES(B)`  -> la patte AURA (a). Attendu `extraDmg[niveau relique]`.
  * `psyker AVANT(A) - psyker AVANT(B)`  -> DOIT etre 0 (pas de parasite = pas de bonus) : c'est la
    CONTRE-EPREUVE du gate `HasEffect`, sans quoi le lot ne conclut rien.
  * `neuro  APRES(A) - neuro  APRES(B)`  -> la patte SELF (b). L'additif defenseur de
    `NeuroparasiteEffect` est IDENTIQUE des deux cotes (il ne depend pas de la relique), donc il
    s'annule dans la difference A-B : ce qui reste EST la patte SELF.

⚠ Le niveau de relique est un ARGUMENT (`--level`, defaut 1) et NON 50 : a 50 le natif clampe au
dernier palier (`extraDmg[10] = 1308`) et l'hypothese << on lit le niveau PASSIF >> rend le MEME
nombre que << on lit le niveau TERTIAIRE >>. Le lot ne conclurait rien (cf. #357).

ASCII only (cp1252). Discipline runner : `--state-file` absolu, `--runner` explicite, dispose en
fin. Usage :
    python probe_1011_norn_crown.py                       # niveau 1
    python probe_1011_norn_crown.py --level 3 --board C4_09 --seed 31337
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
import gameconfig as GC                                                  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
NEURO = "tyranNeurothrope"
ALLY = "astraPrimarisPsy"
TARGET = "orksNob"
FAR = "orksRuntherd"
#: SECOND porteur du trait `Synapse` (Tyranids, au pool). Il n'entre QUE dans les bras `*+2S` : il
#: sert a trancher la patte SELF, qui depend de l'existence d'un emetteur AUTRE que le sujet
#: (`GetSurroundingUnits(..., includeCenter: false)`).
SECOND_SYNAPSE = "tyranParasite"
PLACES = {NEURO: (3, 2), ALLY: (3, 3)}
SECOND_PLACE = (2, 2)                       # 1 hex du Neurothrope, dans la bulle (rayon 2)
A_PLACES = {TARGET: (3, 4), FAR: (0, 5)}
NEUROPARASITE = "Neuroparasite"


def _build(state: Path, board: str, seed: int, relic_level, hp_target: int,
           second_synapse: bool) -> int:
    """`rl_duel build` avec placement EXPLICITE des quatre unites. `relic_level=None` = bras B
    (aucune relique) -- c'est le SEUL ecart entre les deux runners.

    ⚠ `--hp-target` n'est PAS un confort : sans lui, `aiPredict` SATURE ses deux bornes aux PV
    RESTANTS de la cible apres l'attaque du Neurothrope (mesure : 3536/3536 des DEUX cotes), et
    l'ecart A-B tombe a 0 pour une raison qui n'a rien a voir avec la relique -- un accord en
    regime DEGENERE, qui ne prouve rien. Il met aussi `Armor`/`FixedArmor` a 0, identiquement des
    deux cotes, donc il ne peut pas fabriquer d'ecart."""
    p_units = [NEURO, ALLY] + ([SECOND_SYNAPSE] if second_synapse else [])
    cmd = [sys.executable, str(Path(__file__).with_name("rl_duel.py")), "build",
           "--seed", str(seed), "--board", board,
           "--p-units", ",".join(p_units),
           "--a-units", ",".join([TARGET, FAR]),
           "--hp-target", str(hp_target),
           "--state-file", str(state), "--no-ai"]
    places = dict(PLACES)
    if second_synapse:
        places[SECOND_SYNAPSE] = SECOND_PLACE
    for uid, (c, r) in places.items():
        cmd += ["--place", "%s:%d,%d" % (uid, c, r)]
    for uid, (c, r) in A_PLACES.items():
        cmd += ["--a-place", "%s:%d,%d" % (uid, c, r)]
    if relic_level is not None:
        cmd += ["--equip-relic", "%s:NornCrown:%d" % (NEURO, relic_level)]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise SystemExit("[1011] build rc=%d\n%s" % (out.returncode, (out.stderr or "")[-2000:]))
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])


def _dv(sid: int, rid: int) -> dict:
    """`decisionView` -- LA vue qui porte les ids attendus par `aiPredict` / `applyAction`
    (`units[].id`, l'id de SQUAD), les abilities et les effets ACTIFS par unite (#100)."""
    return _rpc(sid, "decisionView", [{"runnerId": rid, "allAbilities": True}]).get("result") or {}


def _units(sid: int, rid: int) -> dict:
    """`{visualId: id de decisionView}` des unites VIVANTES. ⚠ Ce n'est PAS l'`entityId`
    d'`observeBattle` : `aiPredict` refuse celui-la (`unit <n> not found`)."""
    return {u["visualId"]: int(u["id"]) for u in (_dv(sid, rid).get("units") or [])
            if u.get("alive")}


def _predict(sid: int, rid: int, uid: int, tid: int) -> tuple:
    """`aiPredict` = le PREVIEW natif `GetAllPredictions` de l'attaque NORMALE. Rend
    `(healthDmgMin, healthDmgMax, brut)`."""
    res = (_rpc(sid, "aiPredict", [{"runnerId": rid, "unitId": uid, "targetId": tid}])
           .get("result") or {})
    p = res.get("pred") or {}
    return (p.get("healthDmgMin"), p.get("healthDmgMax"), res)


def _normal_attack_type(dv: dict, uid: int) -> "int | None":
    """L'id CONCRET de l'attaque normale de l'unite (`NormalAttackType`), LU dans la vue
    (`abilities[].kind == "normal"`) -- jamais devine : il est PAR UNITE (cf.
    `project_ability_normal_attack_concrete`)."""
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) != int(uid):
            continue
        for ab in (u.get("abilities") or []):
            if ab.get("kind") == "normal":
                return int(ab["id"])
    return None


def _effect_names(dv: dict, uid: int) -> list:
    """Noms d'effets ACTIFS portes par `uid` (`decisionView.units[].effects`, ground truth #100)."""
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            return [e.get("name") for e in (u.get("effects") or []) if e.get("name")]
    return []


def _run(sid: int, state: Path, board: str, seed: int, relic_level, label: str,
         hp_target: int, second_synapse: bool = False) -> dict:
    rid = _build(state, board, seed, relic_level, hp_target, second_synapse)
    try:
        u = _units(sid, rid)
        neuro, ally, tgt = u.get(NEURO), u.get(ALLY), u.get(TARGET)
        if None in (neuro, ally, tgt):
            raise SystemExit("[1011] %s : unites introuvables %r" % (label, u))
        dv0 = _dv(sid, rid)
        porteur_eff = _effect_names(dv0, neuro)
        before_ally = _predict(sid, rid, ally, tgt)
        before_neuro = _predict(sid, rid, neuro, tgt)
        at = _normal_attack_type(dv0, neuro)
        if at is None:
            raise SystemExit("[1011] %s : attaque normale du Neurothrope introuvable" % label)
        _rpc(sid, "applyAction", [{"runnerId": rid,
                                   "action": {"kind": "ability", "casterId": neuro,
                                              "targetId": tgt, "abilityType": at}}], timeout=60)
        eff = _effect_names(_dv(sid, rid), tgt)
        after_ally = _predict(sid, rid, ally, tgt)
        after_neuro = _predict(sid, rid, neuro, tgt)
        return {"label": label, "runnerId": rid, "relic": relic_level,
                "neuro": neuro, "ally": ally, "tgt": tgt,
                "porteur_effects": porteur_eff, "norn_pose": "NornCrown" in porteur_eff,
                "tgt_effects": eff, "parasite": NEUROPARASITE in eff,
                "ally_before": before_ally[:2], "ally_after": after_ally[:2],
                "neuro_before": before_neuro[:2], "neuro_after": after_neuro[:2],
                "raw_ally_after": after_ally[2]}
    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}])


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--hp-target", type=int, default=200000,
                    help="PV forces de la cible : SANS lui, aiPredict sature ses bornes aux PV "
                         "restants et l'ecart A-B est un ZERO DEGENERE (cf. _build)")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    outdir = ROOT / "logs"
    outdir.mkdir(parents=True, exist_ok=True)
    ra = _run(sid, outdir / "st_1011_A.json", a.board, a.seed, a.level,
              "A relique niv %d" % a.level, a.hp_target)
    rb = _run(sid, outdir / "st_1011_B.json", a.board, a.seed, None,
              "B sans relique", a.hp_target)
    # Bras +2S : un SECOND porteur `Synapse` a 1 hex du Neurothrope. Il ne change RIEN a la patte
    # AURA (l'allie avait deja le Neurothrope pour emetteur) ; il n'existe que pour trancher la
    # patte SELF, qui exige un emetteur AUTRE que le sujet (`includeCenter: false`).
    ra2 = _run(sid, outdir / "st_1011_A2.json", a.board, a.seed, a.level,
               "A+2S relique niv %d" % a.level, a.hp_target, second_synapse=True)
    rb2 = _run(sid, outdir / "st_1011_B2.json", a.board, a.seed, None,
               "B+2S sans relique", a.hp_target, second_synapse=True)

    curve = ((GC.ability("NornCrown") or {}).get("variables") or {}).get("extraDmg") or []
    attendu = curve[a.level - 1] if 0 < a.level <= len(curve) else None
    clampe = curve[-1] if curve else None

    print("[1011] extraDmg attendu au niveau %d = %s   (palier CLAMPE niveau 50 = %s)"
          % (a.level, attendu, clampe))
    for r in (ra, rb, ra2, rb2):
        print("[1011] %-22s runner=%-4s NornCrown_pose=%s parasite_sur_cible=%s effets_cible=%s"
              % (r["label"], r["runnerId"], r["norn_pose"], r["parasite"], r["tgt_effects"]))
        print("        allie  AVANT=%s APRES=%s" % (r["ally_before"], r["ally_after"]))
        print("        neuro  AVANT=%s APRES=%s" % (r["neuro_before"], r["neuro_after"]))

    def d(x, y):
        if x is None or y is None:
            return None
        return x - y

    def ecarts(x, y, titre):
        print("[1011] --- %s (isolent NornCrown, tout le reste est identique) ---" % titre)
        print("        allie  AVANT (contre-epreuve, DOIT etre 0) : min=%s max=%s"
              % (d(x["ally_before"][0], y["ally_before"][0]),
                 d(x["ally_before"][1], y["ally_before"][1])))
        print("        allie  APRES (patte AURA)                  : min=%s max=%s"
              % (d(x["ally_after"][0], y["ally_after"][0]),
                 d(x["ally_after"][1], y["ally_after"][1])))
        print("        neuro  APRES (patte SELF)                  : min=%s max=%s"
              % (d(x["neuro_after"][0], y["neuro_after"][0]),
                 d(x["neuro_after"][1], y["neuro_after"][1])))

    ecarts(ra, rb, "ECARTS A - B   (Neurothrope SEUL porteur Synapse)")
    ecarts(ra2, rb2, "ECARTS A2 - B2 (un SECOND porteur Synapse a 1 hex)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
