"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r6 -- LE BLAST RADIUS, ET LA CLASSE QUE LA FICHE DECLARAIT LA PLUS
VISIBLE : la famille REVIVE. Sa premisse est FAUSSE, et le decompile la refute.

CE QUE LE RESIDU ET LE §6 AFFIRMENT
------------------------------------
Residu : « la famille **revive** -- cette derniere etant la seule capable d'**annuler** un crush
(garde revive de `KillUnitOperation$$Execute`), donc la plus visible si le port divergeait. »

§6 de `case-462-r4b-r1-r1-r1-r1-c-r3-r1-r1-emission-crush.md` : « Les quatre revives (`Narthecium`,
`TaintedNarthecium`, `ReanimationBeam`, `RitesOfMorkai`, `PhoenixGem`) visent le **mourant** :
`CanBeRevived` passe sur un decoy (ni `PermaDeath` ni `Mechanical`), donc un apothicaire adjacent
**peut** annuler un crush ».

CE QUE LE DECOMPILE DIT
------------------------
`IdunBattle.Core.Services.BattleQuery$$CanBeRevived(target, healType)`, lu verbatim :

    GetStat(target, 5 = Health) < 1
    && UnitExtensions.IsAffectedByHealType(target, healType)
    && !UnitExtensions.HasFlag(target, 0xd)                     <-- L'ETAGE QUE LE §6 SAUTE
    && !UnitExtensions.HasTrait(target, 0x41a = PermaDeath)
    && !UnitExtensions.HasHealBlockers(target)

`0xd = 13 = UnitFlag.PreventRevive` (`data/symbols/t6dpr4k06g/frida/enums.tsv`, LU -- pas deduit du
nom). Le §6 enumere `PermaDeath` et le heal-type et **oublie ce flag-la**.

Or `IdunBattle.Operations.KillUnitOperation$$Execute` le POSE, et son gate est LU :

    bool preventRevive = options.<+0x45> ? true : UnitExtensions.IsSteppable(killed);
    if (options.<+0x46> && CanBeOverkilled(killed))  flags.Add(0x08 = Overkilled);
    if (preventRevive)                               flags.Add(0x0d = PreventRevive);

et `IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` ecrit
`*(undefined2 *)(opts + 0x44) = 0x101`, donc **`+0x45 = 1`**.

LE RANG TRANCHE TOUT, et il est LU aux adresses de retour de `Execute` :

    RecordDeathReason                    (gate +0x44)
    flags.Add(0x08 = Overkilled)         (gate +0x46 && CanBeOverkilled)
    flags.Add(0x0d = PreventRevive)      <-- ICI
    On(1 = PreUnitDeath)                 <-- LE VECTEUR QUI PORTE LES REVIVES
    <lecture de UnitComponent+0xa8 = PendingRevive>   <-- LA GARDE REVIVE
    On(2) / Add(6 = Dead) / RemoveEffects(0) / RemoveEffects(1) / On(0) / On(0x36) /
    RemoveEffects(2) / +0xa8 = 0 / On(0x35)

⇒ le flag est pose **AVANT** le vecteur qui declenche les revives. Donc :

  * **UN CRUSHE NE PEUT JAMAIS ETRE REVIVE** -- `+0x45 = 1` arme `PreventRevive` sans condition.
    La premisse du residu (« la seule capable d'annuler un crush ») est REFUTEE ;
  * et hors crush, sous `ForDefault` (tout a zero), `preventRevive = IsSteppable(killed)` : **tout
    Steppable mort, quelle qu'en soit la cause**, est marque irrevivable.

CE QUE LE PORT FAIT
--------------------
`revive_effect.py::can_be_revived` porte quatre des cinq etages et ecrit, pour le cinquieme :
« Flag 0xd (**pas encore pose a l'instant de l'OnPreDeath**) [...] -> non-bloquant ». C'est une
JUSTIFICATION ECRITE, et elle est FAUSSE : le rang ci-dessus montre l'inverse. Le port accepterait
donc de ressusciter un crushe que le natif refuse.

CE PROBE MESURE CET ECART, PAR ETAGE, AVANT toute correction.

    python probe_462r4br6_revive_apres_crush.py --board C4_09
"""
from __future__ import annotations

import argparse
import pathlib
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import probe_448r1r1r2r2_gates_abandon as GA                                   # noqa: E402
import probe_448r1r1r3_double_parcours as DP                                   # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                        # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state     # noqa: E402
from engine.runner.components import (HealthComponent, UnitComponent,          # noqa: E402
                                      UnitFlagsComponent)
from engine.runner.events import EventBus                                      # noqa: E402
from engine.runner.operations.movement import MoveUnitOperation                # noqa: E402
from engine.runner.operations.triggers.revive_effect import can_be_revived     # noqa: E402

PREVENT_REVIVE = 13                  # `UnitFlag.PreventRevive`, LU dans `frida/enums.tsv`


def _voisines(board):
    neigh, walk, _e = board.walk_maps_by_pos()
    for a in sorted(q for q, w in walk.items() if w):
        vs = [q for q in (neigh.get(a) or ()) if walk.get(q)]
        if vs:
            return a, sorted(vs)[0]
    return None, None


def volet(board_id: str) -> int:
    bad = 0
    board = GA._load_board(board_id)
    a, b = _voisines(board)
    if a is None:
        print("[R6] SANS OBJET : pas de couple de tuiles voisines walkable sur %s" % board_id)
        return 1
    print("[R6] board %s : mover en %s, STEPPABLE allie en %s" % (board_id, a, b))

    # --- LE CRUSH, par la voie REELLE (`MoveUnitOperation` -> `KillSteppableUnits`).
    st = DP._state(board, [(1, a, 1, []), (2, b, 1, [UnitTrait.Steppable])])
    # PV a 1 : un Steppable natif nait a 0 PV (une mine) ou a 1 (un decoy). On prend 1 pour que
    # « hp < 1 » ne soit VRAI qu'a cause du crush -- sinon `can_be_revived` passerait son premier
    # etage AVANT meme la mort, et le bras ne mesurerait rien.
    st.get_entity(2).get_component(HealthComponent).hp = 1
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    e2 = st.get_entity(2)
    uc2 = e2.get_component(UnitComponent)
    hc2 = e2.get_component(HealthComponent)
    fl2 = e2.get_component(UnitFlagsComponent)
    flags = sorted(getattr(fl2, "flags", None) or ())
    print("[R6] apres le move : crushes=%s  alive=%s  hp=%s  flags=%s"
          % ([t["unit"] for t in op.last_crushed], uc2.alive, hc2.hp, flags))
    ok = ([t["unit"] for t in op.last_crushed] == [2] and not uc2.alive and hc2.hp == 0)
    bad += 0 if ok else 1
    print("[R6] %-56s => %s" % ("le crush a bien eu lieu", "OK" if ok else "MONTAGE INERTE"))
    if not ok:
        print("[R6] sans crush, la suite ne prouverait rien")
        return bad

    # --- ETAGE 1 : le FLAG natif est-il pose cote port ?
    pose = PREVENT_REVIVE in flags
    print("[R6] %-56s => %s"
          % ("`UnitFlag.PreventRevive` (0xd) pose sur le crushe",
             "OUI" if pose else "NON  <-- ECART, le natif le pose sous `+0x45 = 1`"))

    # --- ETAGE 2 : le LECTEUR. `can_be_revived` doit rendre FAUX (le natif refuse).
    ent = entities_from_state(st, 1, target_id=2, actor_id=1)
    # `ent.target` = l'unite MOURANTE (`AbilityEntities+0x178`), la voie par laquelle le natif la
    # passe a `CanBeRevived` sur un `OnPreDeath`. `ent.units` ne la porte PAS : elle est morte.
    cible = ent.target
    if cible is None:
        print("[R6] la cible n'est pas dans le contexte DSL -- NON MESURE")
        return bad + 1
    verdict = can_be_revived(ent, cible, 2, st, heal_type=0)
    print("[R6] `can_be_revived(crushe)` -> %s   (natif : FAUX, `!HasFlag(0xd)` echoue)" % verdict)
    ok = (verdict is False)
    bad += 0 if ok else 1
    print("[R6] %-56s => %s"
          % ("le port REFUSE de revive un crushe",
             "OK" if ok else "ROUGE -- le port ressusciterait un crushe"))

    # --- ETAGE 3 : LE TEMOIN. Une unite ORDINAIRE morte (non Steppable, non crushee) DOIT rester
    # revivable, sinon le correctif serait un refus INVENTE au lieu d'un mirror.
    st2 = DP._state(board, [(1, a, 1, []), (3, b, 1, [])])
    e3 = st2.get_entity(3)
    e3.get_component(UnitComponent).alive = False
    e3.get_component(HealthComponent).hp = 0
    ent2 = entities_from_state(st2, 1, target_id=3, actor_id=1)
    cible2 = ent2.target
    v2 = can_be_revived(ent2, cible2, 3, st2, heal_type=0) if cible2 is not None else None
    ok = (v2 is True)
    bad += 0 if ok else 1
    print("[R6] TEMOIN  `can_be_revived(mort ORDINAIRE)` -> %s => %s"
          % (v2, "OK (le gate ne mord QUE sur le regime vise)" if ok else "ROUGE"))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C4_09")
    a = ap.parse_args()
    bad = volet(a.board)
    print("\n[462-...-r6] %s (%d rouge(s))" % ("OK" if bad == 0 else "ROUGE", bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
