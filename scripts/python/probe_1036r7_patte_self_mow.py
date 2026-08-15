"""#1036-r7 -- LA PATTE SELF DES DEUX AURAS MYTHIQUES DE MoW : le regime est-il ATTEIGNABLE ?

Le residu annonce que le natif accorde le bonus au PORTEUR quand il attaque lui-meme
(`Friends(Owner, AllUnits)` n'exclut pas le porteur, et pour `1548 GuardianConstruct` la branche
SOURCE d'`EffectTargetType.Both = 6 = 2|4` le retient des qu'il a repare quelqu'un).

CE PROBE NE PORTE RIEN. Il MESURE les trois entrees dont le port aurait besoin, sur un runner LIVE,
parce que chacune peut rendre le regime INERTE cote port -- et qu'une seule d'entre elles suffit :

  1. `_unit_rarity(state, <MoW>)` -- le 3e etage du selecteur est `UnitsWithRarity(., Mythic)`, et
     le port lit `StatsComponent.ctx.rarity`. TRI-ETAT : `None` = NON MESURE -> gate FERME.
     `snapshot._load_machine_stats` bat le `UnitContext` d'une Machine depuis la ligne
     `entityType == Machine` de `combatSnapshot`, donc la rarete n'y est que si le capteur #1039 la
     publie sur CETTE ligne-la.
  2. la branche `& 4` d'`EffectTargetType.Both`. LU :
     `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects` fait
     `if (targetType & 2) IsTargetOfOneOfEffects(...)` PUIS `if (targetType & 4)
     IsOwnerOfOneOfEffects(...)`, et `IdunBattle.Core.Services.EffectsQuery$$IsOwnerOfOneOfEffects`
     enumere l'`EffectsOwnedComponent` de l'entite (composant `+0x10`, `EffectType` a `<effet>+0x58`,
     `IsActive` a `+0x5c` sous `onlyActive`). Cote port, le canal `att_effect_names` du ctx d'AURA
     est `_target_effect_names`, qui lit `EffectsState.by_unit` -- c'est-a-dire la branche `& 2`
     SEULE. La branche SOURCE n'a AUCUN canal.
  3. la MoW peut-elle ATTAQUER ? Une MoW a `weapons = []` et `stats.Damage = 0` : elle n'a AUCUNE
     attaque normale, son degat vient de ses ACTIVES (`ReanimationBeam` porte `dmgPct`/`maxDmg`).

Sortie ASCII stricte. rc 0 = mesure faite (quel qu'en soit le verdict), rc 1 = mesure impossible.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import rl_duel as R                                                             # noqa: E402


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


class _Session:
    """MEME patron que `probe_1036r1_guardian_construct_live._Session` -- y compris
    `bind_ambient_rpc`, sans lequel `collect_triggered_abilities` retombe sur le gameconfig du
    greffon et le port est AMPUTE de la mythique (#448-r3-r1)."""

    def __init__(self, rid: int):
        import rl_collect_batch as B                                            # noqa: PLC0415
        self._B = B
        self.sid = B._resolve_session()
        self.rid = int(rid)
        B.bind_ambient_rpc(self.sid)

    def rpc(self, method, body=None, timeout=90):
        b = dict(body or {})
        b.setdefault("runnerId", self.rid)
        return _unwrap(self._B._rpc(self.sid, method, [b], timeout=timeout)) or {}

    def dispose(self):
        try:
            self._B._rpc(self.sid, "disposeRunner", [{"runnerId": self.rid}], timeout=20)
        except Exception:                    # un teardown qui leve masquerait le verdict
            pass

MOW = "necroReanimator"
MYTHIC = "GuardianConstruct"
NIVEAU = 4
BOARD = "MC1_67"
SEED = 777
#: `EffectType` 0x609 = 1545 -- l'effet que `NanoscarabRepairProtocolsAbility$$ExecuteBehaviour`
#: pose sur la cible reparee, et dont la MoW est la SOURCE.
REPAIR = "NanoscarabRepairProtocols"


def _build() -> int:
    sf = _HERE.parents[1] / "logs" / "probe1036r7_patte_self.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--p-mow", MOW,
            "--equip-mythic", "%s:%s:%d" % (MOW, MYTHIC, NIVEAU),
            "--state-file", str(sf)]
    print("[1036-r7] build %s" % " ".join(argv))
    if R.main(argv) != 0:
        raise RuntimeError("build ECHOUE : %s" % " ".join(argv))
    rid = json.loads(sf.read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        raise RuntimeError("build sans runnerId : %s" % sf)
    return rid


def main() -> int:
    s = None
    try:
        s = _Session(_build())
        dv = s.rpc("decisionView", {"includeInactive": True})
        cs = s.rpc("combatSnapshot", {})
        ob = s.rpc("observeBattle", {}, 40)
        from engine.runner.snapshot import load_state
        from engine.runner.damage_model import _unit_rarity
        from engine.runner.components import EffectsOwnedComponent, StatsComponent
        state = load_state(dv, ob, cs)

        mow = next((m for m in (dv.get("mows") or []) if m.get("visualId") == MOW), None)
        if mow is None:
            print("[1036-r7] ECART : la MoW %s n'est pas dans dv.mows (%r)"
                  % (MOW, [m.get("visualId") for m in (dv.get("mows") or [])]))
            return 1
        mid = int(mow["casterId"])
        print("[1036-r7] MoW %s = entite %d" % (MOW, mid))

        # --- 1. RARETE, telle que le PORT la lit (foyer COMBAT `_unit_rarity`) ---------------
        r = _unit_rarity(state, mid)
        print("[1036-r7] ETAGE 3 `UnitsWithRarity(., Mythic)` -- _unit_rarity(MoW) = %r" % (r,))
        # la ligne BRUTE du capteur, pour distinguer << canal muet >> de << port qui ne la lit pas >>
        ligne = next((u for u in (cs.get("units") or []) if u.get("entityId") == mid), None)
        print("[1036-r7]   ligne combatSnapshot de la MoW : %s"
              % ("ABSENTE" if ligne is None
                 else "rarity=%r entityType=%r" % (ligne.get("rarity"), ligne.get("entityType"))))
        ent = state.get_entity(mid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        print("[1036-r7]   StatsComponent present : %s ; ctx.rarity = %r"
              % (sc is not None, getattr(getattr(sc, "ctx", None), "rarity", None)))

        # --- 2. branche SOURCE (`& 4`) : la MoW est-elle OWNER d'un effet de reparation ? ------
        eoc = ent.get_component(EffectsOwnedComponent) if ent is not None else None
        owned = list(getattr(eoc, "effects", ()) or ()) if eoc is not None else None
        print("[1036-r7] ETAGE 2 branche SOURCE `& 4` -- EffectsOwnedComponent = %r" % (owned,))
        by_unit = getattr(state.effects, "by_unit", {}) if state.effects is not None else {}
        portes = [getattr(e, "name", None) for e in (by_unit.get(mid) or [])]
        print("[1036-r7]   branche CIBLE `& 2` (`_target_effect_names`) = %r" % (portes,))
        print("[1036-r7]   l'effet %s est-il DANS l'un des deux ? cible=%s source=%s"
              % (REPAIR, REPAIR in (portes or ()),
                 owned is not None and REPAIR in owned))

        # --- 3. la MoW peut-elle attaquer ? ----------------------------------------------------
        actives = [a.get("name") or a.get("abilityId") for a in (mow.get("abilities") or [])]
        print("[1036-r7] ETAGE 0 -- actives publiees de la MoW : %r" % (actives,))
        return 0
    except Exception as exc:                                            # noqa: BLE001
        print("[1036-r7] ECHEC : %s: %s" % (type(exc).__name__, exc))
        return 1
    finally:
        if s is not None:
            s.dispose()
            print("[1036-r7] runner %d dispose" % s.rid)


if __name__ == "__main__":
    raise SystemExit(main())
