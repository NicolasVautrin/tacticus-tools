"""#477-r11 -- le FORMAT REEL du flux de replay natif : grammaire, couverture,
determinisme, canal PRNG, et decoupage en pas.

    python probe_477r11_replay_stream_format.py --session 6 --board C1_70

CE QUE CE PROBE MESURE -- et pourquoi chaque etape existe
--------------------------------------------------------
L'enregistreur natif est arme depuis #653 (`rl_duel build --record-replay`). La
question ouverte n'est plus « peut-on lire le flux » mais « que vaut-il comme
ORACLE » : sa grammaire, ce qu'il couvre, ce qu'il OMET, et s'il est reproductible.

  Etape 1 -- GRAMMAIRE. Le flux est parse par une grammaire STRICTE derivee du
     producteur `IdunBattle.BattleStream.Loggers.StreamCache`. Toute ligne qui
     n'entre dans aucune des quatre formes fait ROUGIR : c'est ainsi qu'on
     apprend qu'une forme nous manque, au lieu de l'ignorer en silence.

  Etape 2 -- COUVERTURE, DERIVEE ET PUBLIEE. Le vocabulaire TOTAL du flux est
     lu dans les trois enums natifs (`data/symbols/<build>/frida/enums.tsv`) :
     `IdunBattle.Streams.GroupType`, `IdunBattle.Streams.StepType`,
     `IdunBattle.Streams.TagKey`. Le probe imprime observe / total ET la liste
     des NON OBSERVES. Un comparateur qui ne compare que ce que les deux cotes
     possedent est une projection IMPLICITE ; ici l'ensemble comparable est
     ECRIT. NON COMPARE != EGAL.
     Deux confrontations DERIVEES completent l'inventaire, parce qu'un enum ne
     dit que ce que le flux SAIT nommer, jamais ce qu'il OMET :
       (a) `IdunBattle.Entities.Enum.StatType` (27 stats) vs les `TagKey`
           `UnitStats_*` -- quelles stats de combat n'ont AUCUN porteur ;
       (b) les cles de `observeBattle` (le canal de comparaison que le projet
           utilise AUJOURD'HUI) vs les `TagKey` -- ce qu'un comparateur de
           replay perdrait par rapport a l'existant.

  Etape 3 -- DETERMINISME. Deux batailles SEQUENTIELLES, meme seed, meme board,
     memes rosters, meme pilotage. Comparaison CARACTERE PAR CARACTERE -- c'est
     exactement ce que fait `Runner.ReplayValidator$$CompareOutputStream` via
     `System.String$$get_Chars`. En cas d'ecart, le probe LOCALISE le premier
     caractere divergent, puis ventile : incidente (normalisable), derivee du
     PRNG, ou essentielle.
     ATTENTION : les deux bras sont joues l'un APRES l'autre, pas en parallele.
     Deux runners coexistants partageraient l'etat du process et un accord
     mesure ainsi serait plus faible.

     CONTRE-EPREUVE OBLIGATOIRE (bras C, seed different). Un « identique » ne
     vaut RIEN sans elle : un capteur qui rendrait une chaine en cache, ou un
     flux degenere, donnerait exactement le meme vert. Le bras C doit DIFFERER
     du bras A ; s'il n'en differe pas, l'egalite A==B ne mesure plus le
     determinisme et le probe ROUGIT.

  Etape 4 -- CANAL PRNG. `Replay$$GetWholeBattleRngEvents` est le SECOND canal
     du validateur natif (`Runner.RngEventComparer$$DoRngEventsDiffer`). Le RPC
     n'en rend aujourd'hui que le COMPTE : le probe mesure donc sa stabilite
     d'un rejeu a l'autre, et DIT que le contenu n'est pas lisible.

  Etape 5 -- DECOUPAGE EN PAS. Affirmation offline a confronter :
     `IdunBattleLogic.Replay.ReplayRecorder$$Listen` ecarte les messages dont le
     joueur courant n'est pas dans `playerIndicesToRecord` (= `[11]` sur notre
     seed BC), donc « le contenu couvrirait toute la bataille mais le decoupage
     suivrait le seul joueur 11 ». Le probe joue les tours UN PAR UN sur un
     unique runner et releve, a chaque tour, le delta de `stepCount` et le delta
     de longueur. Contenu et decoupage se separent alors par la mesure.

     DEUX PIEGES d'attribution, tous deux mesures ici, tous deux capables
     d'inverser le verdict :
       * `Match_CurrentPlayerId` / `Match_PreviousPlayerId` portent un ID
         D'ENTITE ECS, pas un `PlayerId`. La correspondance se lit dans le flux
         lui-meme (`Action=AddPlayer Entity=E` + `Tag=Player_Id:P`) et le probe
         la CONSTRUIT ; la lire a l'envers attribue le tour au mauvais joueur ;
       * le joueur qui vient de jouer est `Match_PreviousPlayerId` du
         `PrepareTurn` qui CLOT le delta, jamais `Match_CurrentPlayerId` (qui
         annonce le joueur SUIVANT).

DISCIPLINE : un seul runner vivant a la fois (budget partage), dispose dans le
`finally`. State-files sous `logs/`, jamais sous `data/`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rl_collect_batch import _rpc  # noqa: E402
from symbols_layout import current_build  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"
SYMBOLS = ROOT / "data" / "symbols"

P_UNITS = ["astraBullgryn"]
A_UNITS = ["thousTzaangor"]
SEED = 777

# APPARIEMENT EXPLICITE `observeBattle` (le canal de comparaison ACTUEL du
# projet) -> ce qui le porte dans le flux de replay. ECRIT, jamais devine par
# homonymie : `hp` n'est homonyme d'aucun `TagKey` et pourtant
# `UnitStats_RemainingHealth` le porte -- un critere par nom aurait rendu
# « 8 champs manquants » la ou il y en a 3.
# `None` = AUCUN porteur dans le flux. C'est CETTE liste qui est le livrable.
OBSERVE_FIELD_CARRIER: dict[str, str | None] = {
    "entityId": "champ `Entity=` de chaque ligne Group=/Action= (pas un Tag)",
    "playerId": "Tag=Unit_Owner_Id (id d'ENTITE du joueur)",
    "teamId": "Tag=Unit_Owner_Id (via la table AddPlayer -> Player_Id)",
    "col": "Tag=Unit_Foot_Tile_Id_1..7, resolu par Tile_Column/Tile_Row des AddTile",
    "row": "Tag=Unit_Foot_Tile_Id_1..7, resolu par Tile_Column/Tile_Row des AddTile",
    "hp": "Tag=UnitStats_RemainingHealth",
    "hpMax": "Tag=UnitStats_MaxHealth",
    "armor": "Tag=UnitStats_RemainingArmor",
    "armorMax": "Tag=UnitStats_MaxArmor",
    "isDead": "Tag=Unit_IsDying + Action=RemoveUnit",
    "squadId": None,
    "visualId": None,
    "rank": None,
}

# --- GRAMMAIRE, derivee du producteur -------------------------------------
# `StreamCache.StartGroup` -> une ligne de groupe ; `.Action` -> une ligne
# d'action a depth+1 puis un `Tag=` par entree du SortedDictionary a depth+2 ;
# `.FinishGroup` -> le litteral de fin. L'unite d'indentation est MESUREE ici,
# pas supposee : la RE offline (#477 §10.7) disait « tabulations », le texte
# reel porte QUATRE ESPACES.
RE_GROUP = re.compile(
    r"^(?P<ind> *)Group=(?P<type>[^ ]*) Entity=(?P<entity>[^ ]*)"
    r" Source=(?P<source>[^ ]*) InitialTarget=(?P<target>.*)$")
RE_ACTION = re.compile(
    r"^(?P<ind> *)Action=(?P<type>[^ ]*) Entity=(?P<entity>.*)$")
RE_TAG = re.compile(r"^(?P<ind> *)Tag=(?P<key>[^:]*):(?P<value>.*)$")
RE_FINISH = re.compile(r"^(?P<ind> *)Finish_Group$")

# Tags dont la VALEUR designe une entite (donc renumerotable : divergence
# INCIDENTE si elle ne porte que la-dessus). Derives par nom depuis
# `IdunBattle.Streams.TagKey` -- cf. `_entity_valued_tags`.
ENTITY_TAG_SUFFIXES = ("_Id", "_Entity", "_Tile_Id", "_Id_1", "_Id_2", "_Id_3",
                       "_Id_4", "_Id_5", "_Id_6", "_Id_7")
ENTITY_TAG_EXCEPT = {
    # Ids de CONFIGURATION (ability/effect/joueur), pas des entites ECS :
    # les renumeroter effacerait une vraie divergence.
    "UnitStats_ActiveAbility_Id", "UnitStats_TriggeredAbility_Id", "Effect_Id",
    "Player_Id", "Match_CurrentPlayerId", "Match_PreviousPlayerId",
    "Unit_Owner_Id", "Shields_Id", "RoomId", "Score_Event_Type",
}


def _ascii(s: str) -> str:
    return s.encode("ascii", "replace").decode("ascii")


def _build_hash() -> str:
    """Le build qui FAIT FOI -- `data/symbols/CURRENT`, jamais « le seul
    repertoire » : plusieurs builds coexistent volontairement (symbols_layout)."""
    return current_build()


def load_enum(build: str, full_name: str) -> dict[int, str]:
    """Lit un enum natif depuis la table VERSIONNEE. Pas de mirror Python : la
    table est la source, et un mirror ajouterait une dette de fraicheur."""
    path = SYMBOLS / build / "frida" / "enums.tsv"
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if parts[0] != full_name or len(parts) < 2:
            continue
        out: dict[int, str] = {}
        for item in parts[1].split(","):
            k, _, v = item.partition("=")
            out[int(k)] = v
        return out
    raise SystemExit("[477-r11] enum absent de la table : %s" % full_name)


def _run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(HERE / "rl_duel.py"), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(HERE))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _build(state_file: Path, board: str, seed: int,
           p_units: list[str], a_units: list[str]) -> tuple[int | None, str]:
    rc, out = _run(["build", "--seed", str(seed), "--board", board,
                    "--p-units", ",".join(p_units),
                    "--a-units", ",".join(a_units),
                    "--record-replay", "--state-file", str(state_file)])
    if rc != 0 or not state_file.exists():
        return None, out
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), out


def _read_stream(sid: int, rid: int) -> dict:
    return (_rpc(sid, "replayOutputStream",
                 [{"runnerId": rid, "maxChars": 8000000}], timeout=90)
            .get("result") or {})


# --- Etape 1 : parse strict ------------------------------------------------

class ParsedStream:
    def __init__(self) -> None:
        self.groups: Counter[str] = Counter()
        self.actions: Counter[str] = Counter()
        self.tags: Counter[str] = Counter()
        self.tag_values: dict[str, set[str]] = {}
        self.unparsed: list[tuple[int, str]] = []
        self.indent_unit: int | None = None
        self.max_depth = 0
        self.line_count = 0
        self.finish_count = 0
        self.newline: str = ""
        self.root_groups: list[str] = []
        self.group_sources: set[str] = set()
        # Actions HORS de tout groupe (profondeur 0) : forme structurelle reelle
        # du flux -- `StreamCache.Action` n'exige aucun groupe ouvert.
        self.actions_hors_groupe: Counter[str] = Counter()
        self.unbalanced: list[str] = []


def parse_stream(text: str) -> ParsedStream:
    ps = ParsedStream()
    # Le separateur de ligne est MESURE sur la chaine RPC, jamais sur un
    # fichier reecrit : Python traduit \n en \r\n a l'ecriture sous Windows,
    # ce qui fabriquerait un CRLF qui n'existe pas dans le natif.
    if "\r\n" in text:
        ps.newline = "CRLF"
    elif "\n" in text:
        ps.newline = "LF"
    elif "\r" in text:
        ps.newline = "CR"
    else:
        ps.newline = "<aucun>"
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    indents: set[int] = set()
    # L'equilibrage se verifie par PILE, jamais par comptes egaux : deux
    # comptes egaux couvriraient un `Finish_Group` sans groupe ouvert suivi
    # d'un groupe jamais ferme.
    stack: list[str] = []
    for i, ln in enumerate(lines):
        if ln == "":
            continue
        ps.line_count += 1
        m = RE_GROUP.match(ln)
        if m:
            ps.groups[m.group("type")] += 1
            indents.add(len(m.group("ind")))
            if not stack:
                ps.root_groups.append(m.group("type"))
            src = m.group("source")
            if src:
                ps.group_sources.add(src)
            stack.append(m.group("type"))
            continue
        m = RE_ACTION.match(ln)
        if m:
            ps.actions[m.group("type")] += 1
            indents.add(len(m.group("ind")))
            if not stack:
                ps.actions_hors_groupe[m.group("type")] += 1
            continue
        m = RE_TAG.match(ln)
        if m:
            k = m.group("key")
            ps.tags[k] += 1
            ps.tag_values.setdefault(k, set()).add(m.group("value"))
            indents.add(len(m.group("ind")))
            continue
        if RE_FINISH.match(ln):
            ps.finish_count += 1
            if not stack:
                ps.unbalanced.append("l.%d Finish_Group sans groupe ouvert" % (i + 1))
            else:
                stack.pop()
            continue
        ps.unparsed.append((i + 1, ln))
    for g in stack:
        ps.unbalanced.append("groupe jamais ferme : %s" % g)
    if indents:
        nz = sorted(x for x in indents if x)
        ps.indent_unit = nz[0] if nz else 0
        ps.max_depth = max(indents)
    return ps


def entity_to_player(text: str) -> dict[str, str]:
    """Table id d'ENTITE -> `PlayerId`, LUE dans le flux.

    `Action=AddPlayer Entity=<E>` est immediatement suivi de
    `Tag=Player_Id:<P>`. Sans cette table, `Match_CurrentPlayerId:4` se lit
    comme « joueur 4 » -- un joueur qui n'existe pas."""
    out: dict[str, str] = {}
    cur: str | None = None
    for ln in text.replace("\r\n", "\n").split("\n"):
        m = RE_ACTION.match(ln)
        if m:
            cur = m.group("entity") if m.group("type") == "AddPlayer" else None
            continue
        m = RE_TAG.match(ln)
        if m and cur and m.group("key") == "Player_Id":
            out[cur] = m.group("value")
            cur = None
    return out


# --- Etape 3 : comparaison et forme canonique ------------------------------

def _entity_valued_tags(tagkey: dict[int, str]) -> set[str]:
    out = set()
    for name in tagkey.values():
        if name in ENTITY_TAG_EXCEPT:
            continue
        if any(name.endswith(s) for s in ENTITY_TAG_SUFFIXES):
            out.add(name)
    return out


def canonicalize(text: str, entity_tags: set[str]) -> str:
    """FORME CANONIQUE : renumerote les ids d'ENTITE dans leur ordre
    d'apparition. La barre du comparateur n'est pas la bit-exactitude du fil,
    c'est l'egalite APRES cette normalisation -- si elle suffit, la divergence
    etait incidente (ordre d'allocation)."""
    mapping: dict[str, str] = {}

    def remap(v: str) -> str:
        if not v or not v.lstrip("-").isdigit():
            return v
        if v not in mapping:
            mapping[v] = "E%d" % (len(mapping) + 1)
        return mapping[v]

    out: list[str] = []
    for ln in text.replace("\r\n", "\n").split("\n"):
        m = RE_GROUP.match(ln)
        if m:
            out.append("%sGroup=%s Entity=%s Source=%s InitialTarget=%s" % (
                m.group("ind"), m.group("type"), remap(m.group("entity")),
                remap(m.group("source")), remap(m.group("target"))))
            continue
        m = RE_ACTION.match(ln)
        if m:
            out.append("%sAction=%s Entity=%s" % (
                m.group("ind"), m.group("type"), remap(m.group("entity"))))
            continue
        m = RE_TAG.match(ln)
        if m and m.group("key") in entity_tags:
            out.append("%sTag=%s:%s" % (m.group("ind"), m.group("key"),
                                        remap(m.group("value"))))
            continue
        out.append(ln)
    return "\n".join(out)


def first_diff(a: str, b: str) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return -1 if len(a) == len(b) else n


def describe_diff(a: str, b: str, label_a: str, label_b: str) -> list[str]:
    idx = first_diff(a, b)
    if idx < 0:
        return ["  IDENTIQUES (%d caracteres)" % len(a)]
    rep = ["  PREMIER ECART au caractere %d (longueurs %d / %d)"
           % (idx, len(a), len(b))]
    la = a[:idx].count("\n") + 1
    rep.append("  ligne %d" % la)
    for lbl, s in ((label_a, a), (label_b, b)):
        start = s.rfind("\n", 0, idx) + 1
        end = s.find("\n", idx)
        end = len(s) if end < 0 else end
        rep.append("    %-6s | %s" % (lbl, _ascii(s[start:end])[:180]))
    # Ventilation par LIGNES divergentes, pas par caracteres.
    la_lines = a.replace("\r\n", "\n").split("\n")
    lb_lines = b.replace("\r\n", "\n").split("\n")
    diff_lines = [(i, x, y) for i, (x, y)
                  in enumerate(zip(la_lines, lb_lines)) if x != y]
    rep.append("  lignes divergentes (position a position) : %d / %d"
               % (len(diff_lines), max(len(la_lines), len(lb_lines))))
    heads: Counter[str] = Counter()
    for _i, x, _y in diff_lines[:5000]:
        st = x.lstrip(" ")
        heads[st.split("=")[0] + ("=" + st.split("=")[1].split(" ")[0]
                                  if "=" in st else "")] += 1
    for k, v in heads.most_common(15):
        rep.append("      %6d  %s" % (v, _ascii(k)[:70]))
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--board", default="C1_70")
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--seed-contre", type=int, default=None,
                    help="seed du bras C (contre-epreuve) ; defaut = seed+1")
    ap.add_argument("--p-units", default=",".join(P_UNITS))
    ap.add_argument("--a-units", default=",".join(A_UNITS))
    ap.add_argument("--skip-steps", action="store_true",
                    help="saute l'etape 5 (decoupage en pas) -- 1 runner de moins")
    a = ap.parse_args()
    sid = a.session
    p_units = [x for x in a.p_units.split(",") if x]
    a_units = [x for x in a.a_units.split(",") if x]
    seed_c = a.seed_contre if a.seed_contre is not None else a.seed + 1
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    build = _build_hash()
    print("[477-r11] build=%s session=%d board=%s turns=%d seed=%d (contre %d)"
          % (build, sid, a.board, a.turns, a.seed, seed_c))
    print("[477-r11] rosters : joueur=%s adversaire=%s"
          % (",".join(p_units), ",".join(a_units)))

    group_enum = load_enum(build, "IdunBattle.Streams.GroupType")
    step_enum = load_enum(build, "IdunBattle.Streams.StepType")
    tag_enum = load_enum(build, "IdunBattle.Streams.TagKey")
    entity_tags = _entity_valued_tags(tag_enum)
    print("[477-r11] vocabulaire NATIF : GroupType=%d StepType=%d TagKey=%d"
          % (len(group_enum), len(step_enum), len(tag_enum)))

    verdicts: list[str] = []
    rc = 0
    runs: list[dict] = []

    # --- Etapes 1 et 3 : trois batailles SEQUENTIELLES ----------------------
    # A et B partagent tout (test de determinisme) ; C ne differe QUE par le
    # seed (contre-epreuve : la comparaison doit encore DISCRIMINER).
    for bras, seed in (("A", a.seed), ("B", a.seed), ("C", seed_c)):
        sf = OUT / ("probe_477r11_%s_%s.json" % (bras, stamp))
        rid = None
        try:
            rid, out = _build(sf, a.board, seed, p_units, a_units)
            if rid is None:
                print("[477-r11] build bras %s KO:\n%s" % (bras, _ascii(out)))
                return 2
            _rpc(sid, "autoPlayRunner", [{"runnerId": rid, "maxTurns": a.turns}],
                 timeout=240)
            res = _read_stream(sid, rid)
            runs.append({"bras": bras, "rid": rid, "res": res})
            print("[477-r11] bras %s (seed %d) runner=%d armed=%s steps=%s "
                  "chars=%s rng=%s"
                  % (bras, seed, rid, res.get("recorderArmed"),
                     res.get("stepCount"), res.get("outputStreamLength"),
                     res.get("rngEventCount")))
        finally:
            if rid is not None:
                try:
                    _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
                except Exception:
                    pass
            try:
                sf.unlink(missing_ok=True)
            except OSError:
                pass

    ta = runs[0]["res"].get("outputStream") or ""
    tb = runs[1]["res"].get("outputStream") or ""
    tc = runs[2]["res"].get("outputStream") or ""
    if not ta or not tb or not tc:
        print("[477-r11] flux VIDE sur au moins un bras -- rien a caracteriser.")
        return 1

    # --- Etape 1 : GRAMMAIRE ------------------------------------------------
    pa = parse_stream(ta)
    print("\n[477-r11] === ETAPE 1 : GRAMMAIRE (bras A) ===")
    print("  separateur de ligne (mesure sur la chaine RPC) : %s" % pa.newline)
    print("  unite d'indentation : %s caractere(s) ESPACE ; profondeur max %d"
          % (pa.indent_unit, pa.max_depth))
    print("  lignes non vides=%d  groupes=%d (dont %d RACINE)  actions=%d "
          "(dont %d hors groupe)  tags=%d  Finish_Group=%d"
          % (pa.line_count, sum(pa.groups.values()), len(pa.root_groups),
             sum(pa.actions.values()), sum(pa.actions_hors_groupe.values()),
             sum(pa.tags.values()), pa.finish_count))
    print("  Source= de groupe (nom SYMBOLIQUE d'ability/effet, pas un id) : %s"
          % ", ".join(sorted(pa.group_sources)[:8]))
    if pa.actions_hors_groupe:
        print("  Action= a profondeur 0 (hors de tout groupe) : %s"
              % ", ".join("%s x%d" % (k, v)
                          for k, v in pa.actions_hors_groupe.most_common()))
    if pa.unparsed:
        rc = 1
        verdicts.append("GRAMMAIRE: %d ligne(s) hors des 4 formes -> une forme "
                        "MANQUE a la grammaire." % len(pa.unparsed))
        for no, ln in pa.unparsed[:10]:
            print("    NON PARSEE l.%d: %s" % (no, _ascii(ln)[:160]))
    else:
        verdicts.append("GRAMMAIRE OK: 100%% des lignes non vides entrent dans "
                        "les 4 formes (Group / Action / Tag / Finish_Group).")
    if pa.unbalanced:
        rc = 1
        verdicts.append("GRAMMAIRE: arbre DESEQUILIBRE -- %s"
                        % " ; ".join(pa.unbalanced[:5]))
    else:
        verdicts.append("GRAMMAIRE OK: arbre equilibre par PILE (%d Group= / %d "
                        "Finish_Group, %d groupes racine)."
                        % (sum(pa.groups.values()), pa.finish_count,
                           len(pa.root_groups)))

    # --- Etape 2 : COUVERTURE derivee et PUBLIEE ---------------------------
    print("\n[477-r11] === ETAPE 2 : COUVERTURE (derivee des enums natifs) ===")
    for label, obs, enum in (("GroupType", pa.groups, group_enum),
                             ("StepType (Action=)", pa.actions, step_enum),
                             ("TagKey (Tag=)", pa.tags, tag_enum)):
        names = set(enum.values())
        seen = set(obs)
        inconnus = seen - names
        print("  %-18s observes %3d / %3d natifs" % (label, len(seen), len(enum)))
        if inconnus:
            rc = 1
            verdicts.append("COUVERTURE: %s -- %d valeur(s) observee(s) ABSENTE(S) "
                            "de l'enum natif : %s (table perimee ?)"
                            % (label, len(inconnus),
                               ", ".join(sorted(inconnus))[:200]))
    print("  (les NON OBSERVES sont ecrits dans le rapport ci-dessous)")

    # (a) STATS SANS PORTEUR -- derive, pas juge a l'oeil : pour chaque membre
    #     de `StatType`, existe-t-il un `TagKey` qui le nomme ?
    stat_enum = load_enum(build, "IdunBattle.Entities.Enum.StatType")
    tag_names = set(tag_enum.values())
    tag_blob = " ".join(tag_names)
    stats_sans_porteur = [s for s in sorted(set(stat_enum.values()))
                          if s not in ("UNUSED_1",) and s not in tag_blob]
    print("  StatType natif : %d membres ; SANS aucun TagKey qui les nomme : %s"
          % (len(stat_enum), ", ".join(stats_sans_porteur) or "(aucun)"))

    cov = OUT / ("replay-stream-couverture-%s.txt" % stamp)
    with cov.open("w", encoding="utf-8") as fh:
        fh.write("# Couverture du flux de replay natif -- build %s\n" % build)
        fh.write("# OBS = valeur VUE dans la bataille mesuree (plancher, pas\n"
                 "#       exhaustif) ; '-' = presente dans l'enum natif, jamais\n"
                 "#       vue ici. NON COMPARE != EGAL.\n\n")
        for label, obs, enum in (("GroupType", pa.groups, group_enum),
                                 ("StepType", pa.actions, step_enum),
                                 ("TagKey", pa.tags, tag_enum)):
            names = sorted(enum.items())
            fh.write("== %s : %d observes / %d natifs ==\n"
                     % (label, len(set(obs)), len(enum)))
            for k, v in names:
                fh.write("  %-4d %-4s %s\n" % (k, "OBS" if v in obs else "-", v))
            fh.write("\n")
        fh.write("== StatType (%d) sans TagKey porteur ==\n" % len(stat_enum))
        for s in stats_sans_porteur:
            fh.write("  %s\n" % s)
    print("  inventaire complet ecrit dans %s" % cov)

    # --- Etape 3 : DETERMINISME -------------------------------------------
    print("\n[477-r11] === ETAPE 3 : DETERMINISME (bras A vs bras B) ===")
    print("  BRUT (caractere par caractere, comme CompareOutputStream) :")
    for ln in describe_diff(ta, tb, "A", "B"):
        print(ln)
    identique = (ta == tb)
    if identique:
        verdicts.append("DETERMINISME: les deux flux sont IDENTIQUES au "
                        "caractere pres (%d caracteres) -- ni ids d'entite ni "
                        "ordre ne bougent d'un rejeu a l'autre." % len(ta))
    else:
        ca = canonicalize(ta, entity_tags)
        cb = canonicalize(tb, entity_tags)
        print("  CANONIQUE (ids d'entite renumerotes a l'apparition) :")
        for ln in describe_diff(ca, cb, "A'", "B'"):
            print(ln)
        if ca == cb:
            verdicts.append("DETERMINISME: divergence INCIDENTE seulement -- "
                            "identiques apres renumerotation des ids d'entite. "
                            "Une FORME CANONIQUE suffit.")
        else:
            rc = 1
            verdicts.append("DETERMINISME: divergence RESIDUELLE apres forme "
                            "canonique -- a ventiler PRNG vs essentielle "
                            "(cf. lignes divergentes ci-dessus).")
        (OUT / ("replay-stream-A-%s.txt" % stamp)).write_text(
            ta, encoding="utf-8", newline="")
        (OUT / ("replay-stream-B-%s.txt" % stamp)).write_text(
            tb, encoding="utf-8", newline="")

    # CONTRE-EPREUVE : sans elle, « A == B » ne prouve pas le determinisme --
    # une chaine mise en cache, ou un flux degenere, rendraient le meme vert.
    print("  CONTRE-EPREUVE (bras C, seed %d) :" % seed_c)
    if tc == ta:
        rc = 1
        verdicts.append(
            "CONTRE-EPREUVE ECHOUEE: le bras C (seed %d) rend un flux IDENTIQUE "
            "au bras A (seed %d). La comparaison ne DISCRIMINE pas -- l'egalite "
            "A==B ne mesure donc rien. Verdict de determinisme SUSPENDU."
            % (seed_c, a.seed))
    else:
        idx = first_diff(ta, tc)
        verdicts.append(
            "CONTRE-EPREUVE OK: un seed different produit un flux different "
            "(1er ecart au caractere %d ; longueurs %d vs %d) -- la comparaison "
            "DISCRIMINE, donc A==B est une mesure." % (idx, len(ta), len(tc)))
        for ln in describe_diff(ta, tc, "A", "C")[:6]:
            print(ln)

    # --- Etape 4 : CANAL PRNG ---------------------------------------------
    print("\n[477-r11] === ETAPE 4 : CANAL PRNG ===")
    ra = runs[0]["res"].get("rngEventCount")
    rb = runs[1]["res"].get("rngEventCount")
    rcc = runs[2]["res"].get("rngEventCount")
    print("  rngEventCount : bras A = %s ; bras B = %s ; bras C (autre seed) = %s"
          % (ra, rb, rcc))
    # Disposition MESUREE en live (RPC `classFields`, cf. la fiche) :
    #   IdunBattle.Utils.PRNG.RngEvent -- Event:String@16, Output:String@24,
    #   StackTrace:String@32, Index:Int32@40 (taille BOXEE 48 => stride 32).
    # Le RPC `replayOutputStream` n'en rend que le COMPTE : le contenu exige un
    # lecteur cote hooks, donc une fenetre de reinject.
    print("  contenu d'un evenement : Event/Output/StackTrace/Index -- NON LU "
          "par le RPC actuel (compte seul).")
    if ra is None or rb is None:
        verdicts.append("PRNG: compte NON MESURE (accesseur non resolu).")
        rc = 1
    elif ra == rb:
        verdicts.append("PRNG OK: meme nombre d'evenements sur les deux rejeux "
                        "(%s). Le CONTENU d'un evenement (Event/Output/"
                        "StackTrace/Index) n'est PAS lisible par le RPC actuel "
                        "-- seul le compte l'est." % ra)
    else:
        rc = 1
        verdicts.append("PRNG: comptes DIFFERENTS (%s vs %s) -- la sequence de "
                        "tirages n'est pas reproductible." % (ra, rb))

    # --- Etape 5 : DECOUPAGE EN PAS ---------------------------------------
    if not a.skip_steps:
        print("\n[477-r11] === ETAPE 5 : DECOUPAGE EN PAS (filtre joueur) ===")
        sf = OUT / ("probe_477r11_steps_%s.json" % stamp)
        rid = None
        try:
            rid, out = _build(sf, a.board, a.seed, p_units, a_units)
            if rid is None:
                print("[477-r11] build etape 5 KO:\n%s" % _ascii(out))
                return 2
            prev = _read_stream(sid, rid)
            e2p = entity_to_player(prev.get("outputStream") or "")
            print("  table entite -> PlayerId, LUE dans le flux : %s"
                  % ", ".join("E%s=P%s" % kv for kv in sorted(e2p.items())))
            if not e2p:
                verdicts.append("DECOUPAGE: table entite->PlayerId VIDE -- "
                                "attribution impossible, etape NON CONCLUANTE.")
                rc = 1
            print("  %-6s %-8s %-8s %-10s %s"
                  % ("tour", "steps", "d_steps", "d_chars", "joueur QUI A JOUE"))
            print("  %-6s %-8s %-8s %-10s %s"
                  % ("init", prev.get("stepCount"), "-",
                     prev.get("outputStreamLength"), "(setup)"))
            rows: list[tuple[int, int, int, str]] = []
            for t in range(1, a.turns + 1):
                _rpc(sid, "autoPlayRunner", [{"runnerId": rid, "maxTurns": 1}],
                     timeout=120)
                cur = _read_stream(sid, rid)
                dsteps = (cur.get("stepCount") or 0) - (prev.get("stepCount") or 0)
                dchars = ((cur.get("outputStreamLength") or 0)
                          - (prev.get("outputStreamLength") or 0))
                delta_txt = (cur.get("outputStream") or "")[
                    (prev.get("outputStreamLength") or 0):]
                # QUI A JOUE ce tour = `Match_PreviousPlayerId` du PrepareTurn
                # qui clot le delta (`Match_CurrentPlayerId` annonce le SUIVANT),
                # traduit par la table entite->PlayerId.
                prevs = re.findall(r"Tag=Match_PreviousPlayerId:(\S+)", delta_txt)
                joueur = e2p.get(prevs[-1], "?E" + prevs[-1]) if prevs else "-"
                print("  %-6d %-8s %-8d %-10d %s"
                      % (t, cur.get("stepCount"), dsteps, dchars, joueur))
                rows.append((t, dsteps, dchars, joueur))
                prev = cur

            # Verdict DERIVE des lignes, jamais suppose. `recorded` = le joueur
            # que `SetupReplayRecorder` retient (PlayerType ni AI ni Environment).
            joues = [r for r in rows if r[2] > 0]
            j_recorded = [r for r in joues if r[3] == "11"]
            j_autres = [r for r in joues if r[3] not in ("11", "-", "?")]
            if not j_autres:
                verdicts.append(
                    "DECOUPAGE: aucun tour joue par un joueur AUTRE que 11 sur "
                    "%d tours -- affirmation NON CONFRONTEE (allonger la "
                    "bataille)." % a.turns)
            else:
                sans_pas = [r for r in j_autres if r[1] == 0]
                avec_texte = [r for r in j_autres if r[2] > 0]
                verdicts.append(
                    "DECOUPAGE: tours joues par un joueur NON enregistre = %d ; "
                    "%d ont produit du TEXTE (donc le CONTENU les couvre) et %d "
                    "n'ont cree AUCUN pas (donc le DECOUPAGE les ignore). "
                    "Tours du joueur 11 : %d, dont %d ont cree un pas."
                    % (len(j_autres), len(avec_texte), len(sans_pas),
                       len(j_recorded), len([r for r in j_recorded if r[1] > 0])))
                if len(sans_pas) == len(j_autres) and all(
                        r[1] > 0 for r in j_recorded):
                    verdicts.append(
                        "DECOUPAGE: affirmation #477 par.10.6 CONFIRMEE par la "
                        "mesure -- contenu complet, decoupage sur le seul "
                        "joueur enregistre.")
                else:
                    rc = 1
                    verdicts.append(
                        "DECOUPAGE: affirmation #477 par.10.6 CONTREDITE -- voir "
                        "le tableau ci-dessus.")

            # --- Etape 2 (volet live) : ce que le canal ACTUEL compare -------
            obs = (_rpc(sid, "observeBattle", [{"runnerId": rid}], timeout=60)
                   .get("result") or {})
            units = (obs.get("units") or [])
            champs = sorted(units[0].keys()) if units else []
            inconnus = [c for c in champs if c not in OBSERVE_FIELD_CARRIER]
            sans_porteur = [c for c in champs
                            if OBSERVE_FIELD_CARRIER.get(c) is None
                            and c in OBSERVE_FIELD_CARRIER]
            print("\n  observeBattle -- %d champs par unite. Appariement au flux :"
                  % len(champs))
            for c in champs:
                porteur = OBSERVE_FIELD_CARRIER.get(c, "<<NON APPARIE>>")
                print("    %-10s -> %s" % (c, porteur if porteur
                                           else "AUCUN PORTEUR DANS LE FLUX"))
            if inconnus:
                # CLIQUET : un champ neuf d'`observeBattle` doit forcer une
                # decision d'appariement, pas passer en silence dans le lot
                # « compare » -- ce serait exactement la projection implicite.
                rc = 1
                verdicts.append(
                    "COUVERTURE: %d champ(s) d'`observeBattle` ABSENT(S) de la "
                    "table d'appariement : %s -- decider s'ils ont un porteur "
                    "dans le flux, puis completer OBSERVE_FIELD_CARRIER."
                    % (len(inconnus), ", ".join(inconnus)))
            verdicts.append(
                "COUVERTURE (live): sur les %d champs par unite d'`observeBattle` "
                "-- le canal de comparaison ACTUEL --, %d n'ont AUCUN porteur "
                "dans le flux : %s" % (len(champs), len(sans_porteur),
                                       ", ".join(sans_porteur) or "(aucun)"))
        finally:
            if rid is not None:
                try:
                    _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
                except Exception:
                    pass
            try:
                sf.unlink(missing_ok=True)
            except OSError:
                pass

    print("\n[477-r11] VERDICTS")
    for v in verdicts:
        print("  - " + _ascii(v))
    print("[477-r11] rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
