#!/usr/bin/env python3
"""#270-d -- POURQUOI `astarLysander` ne se deployait pas, mesure par A/B a UN SEUL BIT d'ecart.

LA CAUSE (decompile = verite, live = confirmation)
--------------------------------------------------
`IdunBattle.Configuration.UnitConfiguration.Traits` est TYPE
`List<IdunBattle.Entities.Enum.UnitTrait>` -- etabli en deux maillons :

  * `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` recopie
    `UnitProperties+0x18` dans `UnitConfiguration+0xd0` (et, si la source est nulle, y pose une
    `List` neuve du meme type) ;
  * `IdunMetaLogic.UserProgress.Model.UnitPropertiesExtensions$$GetPlayerFacingTraits` lit ce MEME
    `UnitProperties+0x18` (son display-class recopie `param_1+0x18` en `+0x28`, qu'il passe a
    `idun.shared.extensions.ListExtensions$$FilterNewList`) et sa signature rend
    `System.Collections.Generic.List<IdunBattle.Entities.Enum.UnitTrait>`.

Un nom hors enum n'est donc pas « un trait que le natif ignorerait » : il est INEXPRIMABLE dans ce
champ. A la relecture du BC :

    `initAndStart` step=deserialize BC (`frida/hooks/features/launch.ts`)
      -> `Newtonsoft.Json.Converters.StringEnumConverter$$ReadJson`  (token String)
      -> `Newtonsoft.Json.Utilities.EnumUtils$$ParseEnum`
      -> `$$MatchName` / `$$FindIndexByName` rendent un `Nullable` VIDE
      -> message bati par `Newtonsoft.Json.Utilities.StringUtils$$FormatWith`,
         `System.ArgumentException` construite puis LEVEE.

Une exception managee levee sous `invokeMethod` remonte cote Frida en « system error » -- d'ou
`[error] initAndStart: system error`, sans autre diagnostic. La faute emporte TOUT le montage (le
BC entier), pas seulement le porteur : c'est ce qui rendait la bissection de #270 lisible
(« il echoue SEUL, les trois autres montent SEULS »).

CE QUI DECLENCHE LE CAS : le gameconfig VIVANT est livre EN AVANCE sur le binaire. Sur
`rnca9r7q6c`, `astarLysander` (releaseStatus 2026-08-26) porte `Subfaction: ImperialFists` alors
que `UnitTrait` s'arrete a quatre sous-factions (DeathKorpsKrieg 9000, FarsightEnclaves 9001,
SistersSilence 9002, BloodRavens 9003).

CE QUE LA PISTE #254 DISAIT, ET POURQUOI ELLE EST REFUTEE
---------------------------------------------------------
La piste soumise etait « le passif `IconOfObstinacy` a `constants: null` et un `GetStringConstant`
leve a la construction de son trigger ». Le `constants` absent est REEL, la levee ne l'est pas :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger`,
`...$$CreateBehaviour`, `...IconOfObstinacy_AddDamageBuffAbility$$CreateBehaviour` et
`...AIconOfObstinacyAbility$$GetAffectedUnits` n'appellent AUCUN `GetStringConstant` /
`GetNumberConstant` -- ils n'utilisent que des litteraux (`DSLTriggers$$On(0x28 = UnitFinishedTurn)`,
`DSLSelectors$$UnitsWithTrait(0x40f)`, effets 0x627/0x628, `DSLFormulas$$TurnsFromRounds(1)`,
`DSLFormulas$$TimesAttackMadeThisTurn`). La seule lecture de constante du kit est
`IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$GetCurrentlyAffectedFriends`
-> `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(0x16)` =
`AbilityConstantType.range`, et le gameconfig la PORTE (`range: "2"`).

LA MESURE
---------
Meme roster, meme board, meme seed, meme seed BC augmente : le SEUL ecart entre les deux bras est
la presence de `ImperialFists` dans `BC.Units[astarLysander].Traits`.

  A  REMIS      -- on re-insere le nom hors enum  -> build attendu KO (« system error »)
  B  TEL QUEL   -- ce que `catalog_inject` produit -> build attendu OK, et `1231 TitanhammerSquad`
                   visible au `decisionView` du porteur

Sortie 0 = A KO et B OK. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYDIR = REPO / "scripts" / "python"
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import catalog_inject  # noqa: E402
import gameconfig as G  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PORTEUR = "astarLysander"
ABILITY_ID = 1231                      # IdunBattle.Entities.Enum.ActiveAbilityType.TitanhammerSquad
FOES = "orksWarboss,orksNob,necroWarden,eldarRanger"
BOARD = "MC1_67"


def _build(seed_bc: Path, state: Path, seed: int, board: str,
           porteur: str = PORTEUR) -> tuple[bool, str]:
    """Lance `rl_duel build`. Rend (le state-file existe, sortie concatenee)."""
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--board", board, "--seed-bc", str(seed_bc), "--state-file", str(state),
           "--p-units", porteur, "--a-units", FOES]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return state.exists(), ((p.stdout or "") + (p.stderr or ""))


def run_cross(porteur: str, faux_trait: str = "ImperialFists", seed: int = 777,
              board: str = BOARD, verbose: bool = False) -> dict:
    """CONTRE-EPREUVE CROISEE : le meme nom hors enum, mais pose sur un AUTRE porteur.

    Pourquoi elle est necessaire. Le A/B de `run()` etablit que RETIRER `ImperialFists` de
    `astarLysander` deverrouille le build -- il n'exclut pas que la faute vienne d'AUTRE CHOSE de
    propre a cette unite (son kit, son passif, son rang) et que le trait n'ait ete qu'un
    co-facteur. On prend donc une unite qui monte DEJA (`votanChampion`, mesure #270) et on lui
    ajoute le meme nom : si elle casse a son tour, la cause est le TRAIT, pas le porteur.

    Rend {`base_ok`: build de l'unite intacte, `spiked_ok`: build avec le nom hors enum ajoute,
    `verbatim`}.
    """
    out = {"porteur": porteur, "faux_trait": faux_trait, "seed": seed, "board": board}
    if faux_trait in catalog_inject.unit_trait_members():
        out["why"] = ("%s est MEMBRE de UnitTrait sur ce build : la contre-epreuve n'a plus de "
                      "nom hors vocabulaire a poser" % faux_trait)
        return out
    sid = _resolve_session()
    tmp = REPO / "logs" / "probe270d"
    tmp.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    bc_base = tmp / ("cross-base-%s.json" % tag)
    bc_spike = tmp / ("cross-spike-%s.json" % tag)
    st_base = tmp / ("cross-sb-%s.json" % tag)
    st_spike = tmp / ("cross-ss-%s.json" % tag)

    catalog_inject.write_augmented_seed_bc(str(bc_base), [porteur])
    doc = json.loads(bc_base.read_text(encoding="utf-8"))
    entry = next(u for u in doc["Units"] if u["Id"] == porteur)
    out["traits"] = list(entry["Traits"])
    entry["Traits"] = [out["traits"][0], faux_trait] + out["traits"][1:]
    bc_spike.write_text(json.dumps(doc), encoding="utf-8")

    try:
        ok_b, _ = _build(bc_base, st_base, seed, board, porteur=porteur)
        out["base_ok"] = ok_b
        if ok_b:
            _rpc(sid, "disposeRunner",
                 [{"runnerId": json.loads(st_base.read_text(encoding="utf-8"))["runnerId"]}],
                 timeout=30)
        ok_s, raw_s = _build(bc_spike, st_spike, seed, board, porteur=porteur)
        out["spiked_ok"] = ok_s
        out["verbatim"] = next((ln.strip() for ln in raw_s.splitlines()
                                if "initAndStart" in ln or "[error]" in ln), "(aucune)")
        if ok_s:
            _rpc(sid, "disposeRunner",
                 [{"runnerId": json.loads(st_spike.read_text(encoding="utf-8"))["runnerId"]}],
                 timeout=30)
    finally:
        for p in (bc_base, bc_spike, st_base, st_spike):
            p.unlink(missing_ok=True)
    if verbose:
        print("CROSS %-16s intact: build %s | + %s : build %s"
              % (porteur, "OK" if out.get("base_ok") else "KO", faux_trait,
                 "OK <-- ECART" if out.get("spiked_ok") else "KO (attendu)"))
        print("      verbatim : %s" % out.get("verbatim", "")[:180])
    return out


def run(seed: int = 777, board: str = BOARD, verbose: bool = False) -> dict:
    """Joue les deux bras. Rend un dict de MESURE (jamais d'assertion ici).

    Cles : `dropped` (noms ecartes), `traits` (ceux qui restent), `a_ok`/`a_verbatim` (bras REMIS),
    `b_ok` (bras tel que produit), `abilities` (ids exposes au decisionView du porteur),
    `carries_ability` (1231 present), `why` (renseignee seulement si le montage n'a pas pu tourner).
    """
    out: dict = {"porteur": PORTEUR, "seed": seed, "board": board}
    gc = G.unit(PORTEUR)
    if gc is None:
        out["why"] = "%s absent du gameconfig" % PORTEUR
        return out
    out["dropped"] = catalog_inject.dropped_traits(gc)

    sid = _resolve_session()
    tmp = REPO / "logs" / "probe270d"
    tmp.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    bc_ok = tmp / ("seedbc-ok-%s.json" % tag)
    bc_ko = tmp / ("seedbc-ko-%s.json" % tag)
    state_a = tmp / ("state-a-%s.json" % tag)
    state_b = tmp / ("state-b-%s.json" % tag)

    catalog_inject.write_augmented_seed_bc(str(bc_ok), [PORTEUR])
    doc = json.loads(bc_ok.read_text(encoding="utf-8"))
    entry = next(u for u in doc["Units"] if u["Id"] == PORTEUR)
    traits_ok = list(entry["Traits"])
    out["traits"] = traits_ok
    if verbose:
        print("session Frida : %d" % sid)
        print("Traits produits  : %s" % traits_ok)
        print("Traits ECARTES   : %s" % out["dropped"])

    if not out["dropped"]:
        # Le jour ou le binaire rattrape le gameconfig, il n'y a plus de bras A a jouer.
        # Ce n'est pas un echec : c'est la fin du regime que ce probe mesure.
        out["why"] = ("le build courant connait deja tous les traits de %s -- plus rien a "
                      "contraster" % PORTEUR)
        bc_ok.unlink(missing_ok=True)
        return out

    doc_ko = json.loads(bc_ok.read_text(encoding="utf-8"))
    entry_ko = next(u for u in doc_ko["Units"] if u["Id"] == PORTEUR)
    # position 1 = juste apres la grande alliance : l'ordre mesure sur les 175 entrees capturees
    entry_ko["Traits"] = [traits_ok[0]] + out["dropped"] + traits_ok[1:]
    bc_ko.write_text(json.dumps(doc_ko), encoding="utf-8")
    out["traits_a"] = entry_ko["Traits"]

    rid = None
    try:
        ok_a, raw_a = _build(bc_ko, state_a, seed, board)
        out["a_ok"] = ok_a
        out["a_verbatim"] = next(
            (ln.strip() for ln in raw_a.splitlines()
             if "initAndStart" in ln or "[error]" in ln), "(aucune ligne d'erreur)")
        if ok_a:                       # bras A monte quand meme : on ne laisse pas fuir le runner
            _rpc(sid, "disposeRunner",
                 [{"runnerId": json.loads(state_a.read_text(encoding="utf-8"))["runnerId"]}],
                 timeout=30)

        ok_b, raw_b = _build(bc_ok, state_b, seed, board)
        out["b_ok"] = ok_b
        if not ok_b:
            out["b_out"] = raw_b[-800:]
        else:
            rid = json.loads(state_b.read_text(encoding="utf-8"))["runnerId"]
            out["runner"] = rid
            dec = (_rpc(sid, "decisionView", [{"runnerId": rid, "allAbilities": True}],
                        timeout=150).get("result") or {})
            ids: set = set()
            for u in (dec.get("units") or []):
                if u.get("visualId") == PORTEUR:
                    ids |= {int(a.get("id")) for a in (u.get("abilities") or [])
                            if a.get("id") is not None}
                    out["unit_id"] = u.get("id")
                    out["pos"] = u.get("pos")
                    # cooldown initial expose -- corrobore la lecture de
                    # `AbilityConstantType.initialCooldownTurns` (gameconfig : "1")
                    out["cooldowns"] = {int(a["id"]): a.get("cooldown")
                                        for a in (u.get("abilities") or [])
                                        if a.get("id") is not None}
            out["abilities"] = sorted(ids)
            out["carries_ability"] = ABILITY_ID in ids
            # ACTIVABLE, pas seulement present : sans cela `1231` resterait invalidable.
            out["to_activate"] = list(dec.get("toActivate") or [])
    finally:
        if rid is not None:
            try:
                _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            except Exception:                                   # pragma: no cover - best effort
                pass
        for p in (bc_ok, bc_ko, state_a, state_b):
            p.unlink(missing_ok=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--cross", default=None, metavar="UNIT_ID",
                    help="contre-epreuve CROISEE : poser le meme nom hors enum sur une unite qui "
                         "monte DEJA (ex. votanChampion) -- attribue la faute au TRAIT, pas au "
                         "porteur")
    a = ap.parse_args()
    if a.cross:
        c = run_cross(a.cross, seed=a.seed, board=a.board, verbose=True)
        if c.get("why"):
            print("NON MESURE : %s" % c["why"])
            return 0
        return 0 if (c["base_ok"] and not c["spiked_ok"]) else 1
    r = run(seed=a.seed, board=a.board, verbose=True)
    if r.get("why"):
        print("NON MESURE : %s" % r["why"])
        return 0 if not r.get("dropped") else 1
    print("")
    print("A  trait REMIS     : build %s" % ("OK <-- ECART" if r["a_ok"] else "KO (attendu)"))
    print("   verbatim        : %s" % r["a_verbatim"][:200])
    print("B  tel que produit : build %s" % ("OK (attendu)" if r["b_ok"] else "KO <-- ECART"))
    if r.get("b_ok"):
        print("   abilities du porteur : %s   cooldowns %s"
              % (r.get("abilities"), r.get("cooldowns")))
        print("   %d TitanhammerSquad expose au decisionView : %s"
              % (ABILITY_ID, r.get("carries_ability")))
        print("   porteur id=%s pos=%s   toActivate=%s"
              % (r.get("unit_id"), r.get("pos"), r.get("to_activate")))
    else:
        print("   sortie          : %s" % r.get("b_out", ""))
    print("")
    print("A KO + B OK => la cause est le nom hors `IdunBattle.Entities.Enum.UnitTrait` dans")
    print("               `BC.Units[].Traits`, pas le passif `IconOfObstinacy` (#254 refutee).")
    return 0 if (not r["a_ok"] and r["b_ok"] and r.get("carries_ability")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
