"""#448-r2b-r1 -- `1238 FearOfTheUnseen_TeleportingIn` rend-il son porteur NON CIBLABLE ?

LE CRAN QUE CE PROBE MESURE. `IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal`
pose `IdunBattle.Entities.Components.UnitFlagsComponent$$Add(0x11)` sur la CIBLE, pour TOUTE
sous-classe -- et `IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_TeleportingInEffect` derive
d'`ATeleportingEffect`, donc d'`UntargetableEffect` (`data/symbols/<build>/frida/classes.tsv`). Le
port POSAIT deja l'effet (`runner/abilities/tyranids.py::fear_of_the_unseen_tree` ->
`AddEffect(1238, ..., Caster())` au cast de `1115 FearOfTheUnseen`) mais son domaine de
non-ciblabilite (`entities/effects/aura_selectors.py::UNTARGETABLE_EFFECT_TYPES`) ne le contenait
pas : le `tyranDeathleaper` restait donc ENUMERABLE comme cible pendant tout son round de
disparition, la ou i2 dit « The Deathleaper vanishes and CANNOT BE TARGETED or damaged for 1
round ». Ecart PERMISSIF -- exactement le genre qu'un entrainement irait exploiter.

POURQUOI DEUX RUNNERS ET PAS UN. Le correctif est RESTRICTIF (il RETIRE des cibles) : un accord
mesure sur un seul bras ne dirait pas si le natif retire u81 A CAUSE de 1238 ou pour une raison de
geometrie. Les deux bras sont donc APPARIES -- meme seed, meme board, meme premier tour, meme
`endturn` -- et ne different que par le CAST de `1115`.

REGIME. Le `tyranDeathleaper` arrive en DEEP STRIKE, sous `1035 TeleportStrike_TeleportingIn` : il
est deja non ciblable par le canal DEJA porte, et `1115` y est en cooldown. Le premier tour sert
donc a le faire ATTERRIR (1035 expire) -- c'est ce qui rend le temoin non nul : entre les deux
etats, u81 est CIBLABLE, et c'est seulement le cast qui doit le retirer.

LECTURE. Apres `endturn`, `decisionView` est rendu du POINT DE VUE du joueur courant, donc de
l'ADVERSAIRE : ses `attackPlans` enumerent ses cibles. u81 y figure (bras temoin) ou pas (bras
cast) -- et c'est la difference des deux qui est la mesure.

    python scripts/python/probe_448_r2b_r1_fear_untargetable.py [--seed 4488] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from rl_collect_batch import _rpc                                        # noqa: E402

DEATHLEAPER = "tyranDeathleaper"
FEAR_OF_THE_UNSEEN = 1115          # ActiveAbilityType.FearOfTheUnseen
P_UNITS = "tyranDeathleaper,tyranTyrantGuard"
A_UNITS = "ultraEliminatorSgt,necroWarden"

#: Placement FORCE (cf. `_bras`) : le porteur et un tireur de portee 3 a distance hex 2.
POS_DEATHLEAPER = (1, 0)
POS_GUARD = (0, 0)
POS_SGT = (3, 0)
POS_WARDEN = (4, 0)


def _duel(state_file: Path, *args: str) -> str:
    """Un appel `rl_duel.py` en sous-processus (meme voie que la discipline runner)."""
    cmd = [sys.executable, str(HERE / "rl_duel.py"), *args, "--state-file", str(state_file)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(HERE))
    return (r.stdout or "") + (r.stderr or "")


def _ids(state_file: Path) -> tuple:
    st = json.loads(state_file.read_text(encoding="utf-8"))
    sess = st.get("session") or {}
    sid = sess.get("sessionId", sess.get("id"))
    if sid is None:
        raise SystemExit("state-file sans sessionId : %s" % sorted(st))
    return int(sid), int(st["runnerId"])


def _deathleaper_id(sortie: str) -> int | None:
    """L'`unitId` du Deathleaper, LU dans la carte (`u<NN> [tyranDeathleaper]`).

    ⚠ Le motif est ANCRE sur le `u<NN>` qui PRECEDE IMMEDIATEMENT le crochet : un simple
    `split(...)[-1]` ramassait l'id d'une AUTRE unite citee plus tot sur la meme ligne, et le probe
    a alors mesure la ciblabilite de `u77` en la nommant `u81`."""
    m = re.search(r"\bu(\d+)\s*\[%s\]" % re.escape(DEATHLEAPER), sortie)
    return int(m.group(1)) if m else None


def _cibles_adverses(sid: int, rid: int) -> set:
    """Les unites que l'ADVERSAIRE (joueur courant apres `endturn`) enumere comme cibles.

    Source = `decisionView(allAbilities: true).attackPlans[].evals[].targetId` -- la STRUCTURE lue
    dans `oracle.build_card` (`attackPlans` est a la RACINE de la vue, et la cible d'un `eval` est
    son `targetId`), c'est-a-dire l'enumeration NATIVE, celle que le flag `UnitFlag.Untargetable`
    (0x11) ampute. Un premier jet lisait `units[].attackPlans[].targets[]` -- structure INVENTEE :
    il rendait `0 cible` sur les DEUX bras, un accord en regime degenere qui n'aurait rien prouve.
    C'est le garde-fou `if not cibles_t` qui l'a dit."""
    res = (_rpc(sid, "decisionView",
                [{"runnerId": rid, "maxRank": 8, "allAbilities": True}],
                timeout=300).get("result") or {})
    if not res.get("ok"):
        raise SystemExit("decisionView KO : %s" % res.get("error"))
    out = set()
    for p in (res.get("attackPlans") or []):
        for ev in (p.get("evals") or []):
            if not (ev.get("ranked") or []):
                continue                       # aucune tuile d'ou frapper : pas une cible ENUMEREE
            tid = ev.get("targetId")
            if tid is not None:
                out.add(int(tid))
    return out


def _bras(caster_le_fear: bool, seed: int, board: str, tag: str) -> tuple:
    """Monte un runner, joue le tour d'atterrissage, CASTE (ou non) `1115`, puis passe la main.

    Rend `(uid du Deathleaper, cibles enumerees par l'adversaire, runner dispose)`."""
    sf = ROOT / "logs" / ("st_448r2br1_%s.json" % tag)
    sf.parent.mkdir(parents=True, exist_ok=True)
    print("[%s] build seed=%d board=%s" % (tag, seed, board))
    # PLACEMENT FORCE. Aux SpawnPoints du board les deux camps sont hors portee et le bras temoin
    # rend 0 cible -- un regime degenere ou l'accord ne prouve rien. On DEPLACE donc les unites au
    # lieu d'accuser la geometrie : l'`ultraEliminatorSgt` (arme de portee 3) est pose a d=2 du
    # Deathleaper, donc il l'ENUMERE tant que rien ne l'en retire.
    out = _duel(sf, "build", "--seed", str(seed), "--board", board,
                "--p-units", P_UNITS, "--a-units", A_UNITS,
                "--place", "tyranDeathleaper:%d,%d" % POS_DEATHLEAPER,
                "--place", "tyranTyrantGuard:%d,%d" % POS_GUARD,
                "--a-place", "ultraEliminatorSgt:%d,%d" % POS_SGT,
                "--a-place", "necroWarden:%d,%d" % POS_WARDEN)
    uid = _deathleaper_id(out)
    if uid is None:
        print(out[-2000:])
        raise SystemExit("[%s] montage RATE : pas de %s dans la carte" % (tag, DEATHLEAPER))
    sid, rid = _ids(sf)
    try:
        # --- tour 1 : ATTERRISSAGE (le `1035` du deep strike expire, `1115` sort du cooldown) ---
        for u in _a_activer(_duel(sf, "view")):
            _duel(sf, "act", "finish", "--unit", str(u))
        _duel(sf, "aiturn")
        vue = _duel(sf, "view")
        if "TeleportStrike_TeleportingIn" in vue:
            raise SystemExit("[%s] REGIME NON ATTEINT : u%d encore en deep strike" % (tag, uid))
        # `[cd<N>]` = encore en cooldown ; sans lui l'ability est prete (le libelle « pret » porte
        # un accent, on ne s'y arrime donc pas).
        if "FearOfTheUnseen(%d) [cd" % FEAR_OF_THE_UNSEEN in vue:
            print(vue[-1500:])
            raise SystemExit("[%s] REGIME NON ATTEINT : 1115 encore en cooldown" % tag)
        # --- le DISCRIMINANT ------------------------------------------------------------------
        if caster_le_fear:
            r = _duel(sf, "act", "ability", "--unit", str(uid), "--caster", str(uid),
                      "--target", str(uid), "--ability", str(FEAR_OF_THE_UNSEEN))
            if "FearOfTheUnseen_TeleportingIn" not in _duel(sf, "view"):
                print(r[-1500:])
                raise SystemExit("[%s] LE CAST N'A PAS POSE 1238 -- montage a revoir" % tag)
        for u in _a_activer(_duel(sf, "view")):
            _duel(sf, "act", "finish", "--unit", str(u))
        _duel(sf, "act", "endturn")
        # ⚠ `endturn` NE BASCULE PAS la vue : `decisionView` est rendu du point de vue du player
        # ATTACHE, pas du joueur courant -- mesure faite, un premier jet lisait toujours MES plans
        # et rendait donc les ennemis {81, 83} comme « cibles adverses ». Le POV adverse s'obtient
        # par un `attach --team 2` sur le MEME runner (la voie du self-play).
        sf2 = sf.with_name(sf.stem + "_pov2.json")
        _duel(sf2, "attach", "--from", str(sf), "--team", "2")
        sid2, rid2 = _ids(sf2)
        cibles = _cibles_adverses(sid2, rid2)
    finally:
        _duel(sf, "dispose")
    return uid, cibles


def _a_activer(vue: str) -> list:
    """Les unites encore activables, LUES dans la carte (`A ACTIVER ... : [81, 83]`)."""
    for ligne in vue.splitlines():
        if "ACTIVER" in ligne and "[" in ligne:
            corps = ligne[ligne.rindex("[") + 1:ligne.rindex("]")]
            return [int(x) for x in corps.replace(" ", "").split(",") if x.strip().isdigit()]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=4488)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()

    uid_t, cibles_t = _bras(False, a.seed, a.board, "temoin")
    uid_c, cibles_c = _bras(True, a.seed, a.board, "cast")
    print("")
    print("=== #448-r2b-r1 : 1238 retire-t-il son porteur de l'enumeration NATIVE ? ===")
    print("  bras TEMOIN (pas de cast) : u%d dans les cibles adverses = %s   %s"
          % (uid_t, uid_t in cibles_t, sorted(cibles_t)))
    print("  bras CAST   (1115 lance)  : u%d dans les cibles adverses = %s   %s"
          % (uid_c, uid_c in cibles_c, sorted(cibles_c)))
    if not cibles_t:
        print("  INCONCLUSIF : le bras TEMOIN n'enumere AUCUNE cible -- regime degenere, un accord")
        print("  n'y prouverait rien. Rapprocher les equipes (board/placement) et rejouer.")
        return 2
    if uid_t not in cibles_t:
        print("  INCONCLUSIF : u%d n'est deja pas ciblable SANS le cast (hors portee ?) -- le"
              % uid_t)
        print("  discriminant ne mord pas. Rapprocher les equipes et rejouer.")
        return 2
    if uid_c in cibles_c:
        print("  ROUGE : le natif ENUMERE encore le porteur apres le cast -- l'inscription de 1238")
        print("  au domaine RETIRE des cibles que le natif GARDE (ecart RESTRICTIF a annuler).")
        return 1
    print("  VERT : le natif RETIRE le porteur des qu'il porte 1238, et le gardait sans. Le")
    print("  domaine `UNTARGETABLE_EFFECT_TYPES` doit donc bien le contenir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
