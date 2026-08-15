"""#477-r35 -- les trois faces MOVE `*NonOwnerPlaybook` dont le GATE est MONTABLE.

    python probe_477r35_non_owner_gates_montables.py --offline-only
    python probe_477r35_non_owner_gates_montables.py --board MC1_67 --seed 777 --montage purge
    python probe_477r35_non_owner_gates_montables.py --board MC1_67 --seed 777 --montage purge-gate
    python probe_477r35_non_owner_gates_montables.py --board MC1_67 --seed 777 --montage mawclaws
    python probe_477r35_non_owner_gates_montables.py --board MC1_67 --seed 777 --montage mawclaws-gate
    python probe_477r35_non_owner_gates_montables.py --board MC1_67 --seed 777 --montage haywire
    python probe_477r35_non_owner_gates_montables.py --board MC1_67 --seed 777 --montage haywire-gate

#477-r33 a laisse **8** faces MOVE non portees. Elles ne se distinguent PAS par leur difficulte de
RE -- les huit corps se lisent -- mais par la MONTABILITE de leur gate. Ce cas porte les trois dont
le gate se monte AUJOURD'HUI, chacune par une voie DIFFERENTE, et DIT pourquoi les cinq autres ne
le sont pas :

  | id   | gate du corps                    | ce qu'il faut monter                              |
  |-----:|----------------------------------|---------------------------------------------------|
  | 1526 | `HasFaction(mover, Votann)`      | un mover Votann -- 9 unites, **0 au pool** -> injection catalogue ; porteur npc/summon -> GREFFE |
  | 1469 | `HasTrait(mover, Summon)`        | le trait ACCORDE (`add_unit_trait`) -- les 59 porteurs de `Summon` sont tous `kind == summons` ; porteur = relique d'un des 4 du pool |
  | 1531 | occupant `Steppable` de la tuile | la MINE `astarSmnHaywireMine` amenee par `--explicit-stats` ; porteur `astarCyrus` hors pool -> GREFFE |

ETAPE 0 (offline, `--offline-only`)
  0a  RECENSEMENT re-derive par le PARENT dans `frida/classes.tsv` -- jamais par le NOM (le compte
      par nom est FAUX de trois facons, cf. #477-r33). Confronte le registre porte au binaire.
  0b  Le `<slot 4>` de `HaywireMineNonOwnerPlaybook`, RELU sur CETTE classe dans le bloc
      `methodPointers` du PE. C'est la question que #477-r33 a explicitement laissee ouverte, et
      elle ne se DEDUIT pas des trois classes lues par #433-r4-r3 : la table est indexee par
      ADRESSE, et un corps fondu n'a qu'un seul proprietaire. Le verdict decide si la clef
      `HaywireMine_EnemyAvoidMine` a un consommateur ou si elle est MORTE.
  0c  Les CLES BC des trois corps, resolues au litteral et confrontees au gameconfig VIVANT.

ETAPE 1 (live) -- geometrie `camp` de #477-r31, REUTILISEE et non reinventee : c'est la seule dont
il est MESURE que `scorerTileTermTrace` couvre les deux bras. Six montages, dont TROIS controles de
gate (`*-gate`) ou le gate DOIT couper.

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from build_pin import BuildPinRefused                                          # noqa: E402
from rl_collect_batch import _resolve_session, bind_ambient_rpc                # noqa: E402
from probe_193c_move_playbook_terms import (_r, _by_tile, _one, _port_leaves,  # noqa: E402
                                            _exiger_build_des_rva, x_port)
from probe_212_spiritual_leader_tile_term import _apply_native_via             # noqa: E402
from probe_477r31_attract_mechanicals_camp import LAYOUTS_CAMP                 # noqa: E402
from probe_477r33_non_owner_registry_gaps import (_build_hash, _concrets,      # noqa: E402
                                                  _faces, _ctor_ids, _pool)

_BASE = "IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybook`1"


# ================================================================================================
# ETAPE 0
# ================================================================================================
def step0(verbeux: bool = True) -> tuple:
    """Recensement re-derive + confrontation au registre porte. Rend `(rc, rec)`."""
    from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS as REG
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T

    build = _build_hash()
    concrets = _concrets(build)
    faces = _faces(build, concrets)
    ids = _ctor_ids(build, concrets)
    # ⚠ `_faces` rend un ENSEMBLE de faces par classe (une classe peut en porter plusieurs), pas
    # une chaine. Le comparer par egalite rend l'ensemble VIDE -- et un recenseur qui rend zero
    # passe pour vert. C'est la faute exacte que ce probe a commise a sa premiere passe ; le
    # garde-fou ci-dessous la rend IMPOSSIBLE a re-commettre en silence.
    move = sorted(c for c, f in faces.items() if "MOVE" in f)
    if verbeux:
        print("[0a] build=%s : %d concrets derives de `%s`, dont %d faces MOVE"
              % (build, len(concrets), _BASE, len(move)))
    if not concrets or not move:
        print("[0a] ROUGE : le recensement rend %d concrets / %d faces MOVE. Un recenseur ne peut "
              "pas rendre ZERO sur ce qu'il n'a pas visite -- la lecture des tables est CASSEE, "
              "pas le binaire." % (len(concrets), len(move)))
        return 1, {"build": build, "move": [], "ids": {}, "portes": [], "reste": []}

    portes, manquants = [], []
    for cls in move:
        aid = ids.get(cls)
        (portes if aid in REG else manquants).append((cls, aid))
    if verbeux:
        print("[0a] registre porte = %d entrees ; faces MOVE couvertes = %d ; NON portees = %d"
              % (len(REG), len(portes), len(manquants)))
        for cls, aid in manquants:
            print("        MANQUANTE  %-46s id=%s" % (cls, aid))

    rc = 0
    neuves = (int(T.MawClawsOfThyrax), int(T.PurgeResponse), int(T.HaywireMine))
    for aid in neuves:
        if aid not in REG:
            print("[0a] ROUGE : %d n'est PAS au registre alors que ce cas la porte" % aid)
            rc = 1
    # `RedemptionOfTheRisen` est ECRITE et volontairement HORS registre (0 porteur, cliquet #419) :
    # la compter comme « non portee » ferait remonter un faux manquant a chaque passe.
    ecrite_hors = {int(T.RedemptionOfTheRisen)}
    reste = [(c, a) for c, a in manquants if a not in ecrite_hors]
    if verbeux:
        print("[0a] restantes APRES ce cas (hors `RedemptionOfTheRisen`, ecrite hors registre) : %d"
              % len(reste))
    return rc, {"build": build, "move": move, "ids": ids, "portes": portes, "reste": reste}


#: `<slot 4>` attendu par classe -- MESURE, pas suppose. Le probe le RE-DERIVE du binaire et
#: compare ; cette table n'existe que pour faire ROUGIR un glissement de build.
SLOT4_ATTENDU = {
    "HaywireMineNonOwnerPlaybook": True,
    "ECogSupportPlaybookNonOwnerPlaybook": False,
    "KustomForceFieldReworkedNonOwnerPlaybook": False,
    "PsychicFortressNonOwnerPlaybook": False,
    "MawClawsOfThyraxNonOwnerPlaybook": False,
    "PurgeResponseNonOwnerPlaybook": False,
}


def step0b(build: str, verbeux: bool = True) -> int:
    """Le `<slot 4>` -- DELEGUE a `probe_477r37_slot4_et_faces_restantes.step0a` (#477-r37).

    ⚠⚠ **LE CRITERE QUI VIVAIT ICI EST RETIRE : IL ETAIT FAUX DES DEUX COTES.** Il lisait l'entree
    qui PRECEDE le `.ctor` dans le bloc `methodPointers` et en tirait la valeur du `<slot 4>` :

      * **faux NEGATIF** -- `NoHidingFromTheWatchersNonOwnerPlaybook` declare le getter APRES son
        `.ctor` ; le critere ne pouvait pas la voir, et elle vaut `true` ;
      * **faux POSITIF** -- il attribuait a `ECogSupportPlaybookNonOwnerPlaybook` et
        `KustomForceFieldReworkedNonOwnerPlaybook` un override explicite `return 0`
        (`Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`). Le `global-metadata.dat` dit
        qu'elles ne DECLARENT rien : cette entree appartient au TYPE PRECEDENT de la table.

    Il rendait donc la bonne VALEUR pour la mauvaise RAISON -- et l'avoir garde aurait re-enseigne
    la mauvaise lecture. Le remplacant lit le NOM du slot (`get_ShouldIncludingEnemiesWhenCalculate`)
    dans le metadata, sur les VINGT-HUIT concrets, et recoupe par trois sources. Le point de
    doctrine que ce cas a etabli est intact : le `<slot 4>` est une donnee PAR CLASSE.

    `build` n'est plus lu (le delegue le re-derive lui-meme) ; il reste dans la signature pour ne
    pas casser les deux appelants."""
    del build                                  # le delegue re-derive le build lui-meme
    from probe_477r37_slot4_et_faces_restantes import step0a as _step0a
    rc, table = _step0a(call=None, verbeux=verbeux)
    for nom, att in sorted(SLOT4_ATTENDU.items()):
        lu = table.get(nom)
        if lu is None:
            print("[0b] ROUGE : %s a disparu du recensement des concrets" % nom)
            rc = 1
        elif bool(lu["valeur"]) != bool(att):
            print("[0b] ROUGE : %s vaut %s au binaire, %s attendu par #477-r35"
                  % (nom, lu["valeur"], att))
            rc = 1
    if verbeux and (table.get("HaywireMineNonOwnerPlaybook") or {}).get("valeur"):
        print("[0b] VERDICT : `HaywireMineNonOwnerPlaybook` est la seule face **MOVE** dont le")
        print("[0b]   `<slot 4>` vaut `true` => le dispatcher lui yielde AUSSI les porteurs")
        print("[0b]   ENNEMIS, donc sa branche `HaywireMine_EnemyAvoidMine` (-30) est ATTEIGNABLE.")
        print("[0b]   (`NoHidingFromTheWatchersNonOwnerPlaybook` le vaut aussi -- face ATTACK, hors")
        print("[0b]    de cette feuille : cf. #477-r37.)")
    return rc


def step0c(verbeux: bool = True) -> int:
    """Les cles BC des trois corps, confrontees au gameconfig VIVANT."""
    from engine.playbook.non_owner import (MawClawsOfThyraxNonOwnerPlaybook as MC,
                                           PurgeResponseNonOwnerPlaybook as PR,
                                           HaywireMineNonOwnerPlaybook as HM)
    import catalog_inject as CI
    tbl = CI.ai_utilities_from_gameconfig() or {}
    cat = (tbl.get("Default") or {}).get("TriggeredAbilitiesNonOwner") or {}
    attendus = {MC.KEY: 5, PR.KEY: 20, HM.KEY_FRIENDLY: -50, HM.KEY_ENEMY: -30}
    rc = 0
    for k, v in sorted(attendus.items()):
        got = cat.get(k)
        etat = "OK" if got == v else "ECART"
        if got != v:
            rc = 1
        if verbeux:
            print("[0c] %-44s gameconfig=%-6s litteral attendu=%-6s %s" % (k, got, v, etat))
    if verbeux:
        print("[0c] `%s` (-30) est la cle de la branche ENNEMI, ATTEIGNABLE parce que le `<slot 4>` "
              "de cette classe vaut `true` (cf. 0b)." % HM.KEY_ENEMY)
    return rc


# ================================================================================================
# ETAPE 1 -- les montages
# ================================================================================================
#: mover de `purge` : HERO `LeaguesOfVotann` HORS pool (les 9 Votann le sont) -> injection catalogue.
#: ⚠ CE CHOIX A ETE PAYE PAR UNE MESURE ROUGE, comme celui de #477-r33. Le premier essaye etait
#: `votanUthar` : son passif `GrimEfficiency` a un
#: `IdunBattle.AI.Playbook.Loki.GrimEfficiencyPlaybook$$CalculateMovementUtilityInStepsInternal`
#: que le port ne rend pas -> **+5 sur 5 des 11 tuiles hookees**, terme ORTHOGONAL au mesurande
#: mais qui interdit l'accord absolu. Le critere est DERIVE (balayage de `ghidra/functions.tsv`
#: sur les abilities des 5 heros Votann) : aucun `*Playbook` a face `CalculateMovementUtilityInSteps*`.
#: Restent `votanBeserk` (`AugmentedAssaultPlaybook` -- `EvaluateNonComparable` SEULEMENT),
#: `votanIronmaster` (`GravitonRiflePlaybook`, idem) et `votanMemnyr` (`IronkinSteeljackPlaybook`,
#: idem) ; `votanUthar` et `votanChampion` ont, eux, une face MOUVEMENT.
PURGE_MOVER = "votanBeserk"
#: mover de controle : meme geometrie, faction NON Votann.
PURGE_MOVER_NOGATE = "eldarAutarch"
#: porteur GREFFE de `PurgeResponse` -- ses seuls porteurs natifs sont npc/summon, et le corps ne
#: lit du porteur QUE sa position (aucune stat, aucun trait) : la greffe est licite (regle NPC).
PURGE_OWNER = "necroWarden"

#: `mawclaws` : porteur AU POOL, relique NON equipee au seed -> etat 2 (`--equip-relic`).
MC_OWNER = "tyranTyrantGuard"
#: mover : n'importe quel hero du pool, a qui on ACCORDE `Summon` (aucune unite du pool ne l'a).
MC_MOVER = "eldarAutarch"

#: `haywire` : porteur GREFFE (le porteur natif `astarCyrus` est hors pool).
HW_OWNER = "necroWarden"
HW_MOVER = "eldarAutarch"
#: la MINE -- SUMMON `Steppable`, amenee par `--explicit-stats`. C'est elle le mesurande.
HW_MINE = "astarSmnHaywireMine"
#: le CONTROLE : un steppable qui N'EST PAS la mine -> `HasUnitId` coupe, le reste est identique.
HW_MINE_NOGATE = "genesSmnDecoy"

#: la cible ENNEMIE neutre et l'AMI neutre -- repris VERBATIM de la geometrie `camp` de #477-r33.
#: `orksNob` en ami neutre y est MESURE sans effet sur le tier comparable (0 desaccord sur 5
#: montages) ; c'est en MOVER qu'il pollue (`SmashaEadPlaybook`), pas en voisin.
TARGET_FOE = "necroWarden"
NEUTRAL_FRIEND = "orksNob"

#: ⚠ DEUX montages annonces au depart ne sont PAS ici, et chacun pour une raison MESUREE :
#:
#: * `mawclaws` / `mawclaws-gate` -- VERROU STRUCTUREL. Le gate de 1469 est `HasTrait(mover,
#:   Summon)`, or `IdunBattle.Entities.UnitExtensions$$IsAutomatic(unit)` est exactement
#:   `HasTrait(0x2 Summon) || HasTrait(0xd Object)`, SANS aucune exemption (pas meme `Hero`), et
#:   c'est le seul filtre de `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute`. Toute
#:   unite qui franchit le gate de 1469 est donc, PAR CONSTRUCTION, jouee au turn-start par cette
#:   operation et n'entre JAMAIS dans la trajectoire d'activation que `aiStepDryRun` marche.
#:   MESURE : trait `Summon` accorde a `eldarAutarch` (pose VERIFIEE, `traitsAfter` le porte),
#:   25 pas, **0 activation du carrier**. Ce n'est ni un porteur non confrontable ni un montage
#:   rate : c'est le harnais qui n'observe pas ce regime. Le gate est exerce OFFLINE, dans les
#:   deux sens, par la garde.
#: * `haywire-gate` -- le CONTROLE du gate `HasUnitId` ne se monte pas en live : la greffe de
#:   `HaywireMine` fait SPAWNER la mine (c'est l'objet de l'ability), des deux cotes, donc des
#:   tuiles minees apparaissent partout ; et le steppable temoin (`genesSmnDecoy`), place a la
#:   position `neutral`, n'a ete hooke a AUCUN des 4 pas mesures -- la trajectoire du carrier
#:   s'en eloigne. Exerce OFFLINE lui aussi. ⚠ Corollaire mesure sur `haywire` : la tuile qui
#:   porte la mesure est une mine SPAWNEE (2,7), pas celle posee a la main en (5,5).
MONTAGES = ("purge", "purge-gate", "haywire")
#: les montages dont le gate DOIT couper PARTOUT -- l'inertie qui en decoule est DECLAREE et
#: assertionnee dans les deux sens. ⚠ `haywire-gate` n'en fait PAS partie, et ce n'est pas un oubli :
#: la greffe fait spawner des mines sur le plateau, donc le gate PASSE ailleurs. Son controle porte
#: sur la TUILE du decoy (`_bras`), pas sur la decision entiere.
MONTAGES_GATE_COUPE = ("purge-gate", "mawclaws-gate")
#: le mutant qui EST la question de chaque montage. S'il ne mord pas : REGIME DEGENERE.
#: ⚠ `haywire` ne se separe PAS sur l'axe du camp : son `<slot 4>` vaut `true`, donc les DEUX
#: camps sont yieldes et `CAMP-DEUX` n'existe pas comme mutant. Son mutant separateur est
#: `SLOT4-OFF` -- l'etat EXACT du port avant la mesure live qui a renverse le verdict.
MUTANT_SEPARATEUR = {"purge": "CAMP-DEUX", "purge-gate": "SANS-GATE",
                     "haywire": "SLOT4-OFF"}


def _layout(board: str) -> dict:
    lay = LAYOUTS_CAMP.get(board)
    if lay is None:
        raise SystemExit("[477-r35] aucune geometrie `camp` pour le board %r (connus : %s)"
                         % (board, ", ".join(sorted(LAYOUTS_CAMP))))
    return lay


def _mover(montage: str) -> str:
    return {"purge": PURGE_MOVER, "purge-gate": PURGE_MOVER_NOGATE,
            "mawclaws": MC_MOVER, "mawclaws-gate": MC_MOVER,
            "haywire": HW_MOVER, "haywire-gate": HW_MOVER}[montage]


def _owner(montage: str) -> str:
    return {"purge": PURGE_OWNER, "purge-gate": PURGE_OWNER,
            "mawclaws": MC_OWNER, "mawclaws-gate": MC_OWNER,
            "haywire": HW_OWNER, "haywire-gate": HW_OWNER}[montage]


def _mine(montage: str) -> str:
    return HW_MINE if montage == "haywire" else HW_MINE_NOGATE


def build_extra(board: str, montage: str) -> list:
    """Les arguments `rl_duel build` du montage -- FOYER UNIQUE, partage avec la garde.

    Geometrie `camp` : carrier au centre, porteur ALLIE d'un cote, porteur ENNEMI en miroir, une
    cible neutre. Le porteur ENNEMI n'est pas decoratif : c'est LUI qui exerce le pre-gate
    `IsFriend` -- sans un bras ennemi, le mutant `CAMP-DEUX` ne peut rien separer."""
    lay = _layout(board)
    mover, owner = _mover(montage), _owner(montage)
    foe_target = "orksNob" if owner == TARGET_FOE else TARGET_FOE
    p_units, a_units = [mover, owner], [owner, foe_target]
    places = [("--place", "%s:%d,%d" % (mover, lay["carrier"][0], lay["carrier"][1])),
              ("--place", "%s:%d,%d" % (owner, lay["ally"][0], lay["ally"][1])),
              ("--a-place", "%s:%d,%d" % (owner, lay["foe"][0], lay["foe"][1])),
              ("--a-place", "%s:%d,%d" % (foe_target, lay["target"][0], lay["target"][1]))]
    extra = []
    if montage.startswith("haywire"):
        # La MINE occupe la tuile `neutral` -- une tuile CANDIDATE du mover : `Steppable` veut dire
        # qu'on peut marcher DESSUS, donc elle reste dans `action_tiles`. `--explicit-stats` amene
        # le summon avec SES traits (dont `Steppable`), ce qu'un spawn de hero ne ferait pas.
        #
        # ⚠ `--allow-zero-spawn-stats` (#419-r1-tr12-r2-r1) : le patch `summon-spawn` de ces deux
        # summons est INTEGRALEMENT NUL, et depuis ce residu `explicit_stats` le REFUSE par defaut.
        # Ici c'est le regime VOULU -- on veut les TRAITS de la mine, pas ses stats -- et c'est
        # aussi la raison mesuree du constat deja ecrit plus haut : « la tuile qui porte la mesure
        # est une mine SPAWNEE (2,7), pas celle posee a la main en (5,5) ». La mine posee a la main
        # arrive a 0 PV. `HaywireMine` ne porte AUCUNE variable de stats ; `genesSmnDecoy` est
        # declare par `SpiritualLeader.unitId_2` (regime `_2`) alors que l'ability ne porte que les
        # variables NUES -- deux causes distinctes, meme symptome.
        mine = _mine(montage)
        p_units.append(mine)
        extra += ["--explicit-stats", mine, "--allow-zero-spawn-stats"]
        places.append(("--place", "%s:%d,%d" % (mine, lay["neutral"][0], lay["neutral"][1])))
    else:
        # L'AMI NEUTRE n'est PAS decoratif : #477-r33 l'a MESURE -- sans lui la trajectoire native
        # ne hooke qu'un seul bras (2 puis 5 tuiles, toutes du bras ENNEMI), et un montage dont un
        # bras n'est pas observe ne separe rien. Re-mesure ici sur `purge` : sans ami neutre,
        # 4 tuiles hookees, bras AMI = 0.
        p_units.append(NEUTRAL_FRIEND)
        places.insert(2, ("--place", "%s:%d,%d"
                          % (NEUTRAL_FRIEND, lay["neutral"][0], lay["neutral"][1])))
    out = ["--seed-bc", "<pose par l'appelant>",
           "--p-units", ",".join(p_units), "--a-units", ",".join(a_units)] + extra
    for flag, val in places:
        out += [flag, val]
    return out + ["--hp-player", "100000", "--hp-target", "100000"]


def _seed_bc_montage(out_path: Path, montage: str) -> Path:
    """Le seed BC du montage -- les trois voies de montage, chacune VERIFIEE et non supposee."""
    import catalog_inject as CI
    bc = CI._load_seed(None)
    mover, owner = _mover(montage), _owner(montage)

    if montage.startswith("purge"):
        # le MOVER Votann est HORS pool -> injection catalogue (etat 3), bloc Unit + configs.
        tmp = out_path.with_suffix(".aug.json")
        p, ajoutees, cfgs = CI.write_augmented_seed_bc(tmp, [PURGE_MOVER], seed_bc=bc)
        bc = json.loads(Path(p).read_text(encoding="utf-8"))
        print("  injection catalogue : unites=%s configs=%s" % (ajoutees, cfgs))
        rep = CI.graft_passive_ability(bc, owner, "PurgeResponse")
        print("  greffe : %s -> PurgeResponse (id %s), %s entree(s) patchee(s), avant=%s"
              % (owner, rep.get("abilityId"), rep.get("unitsPatched"), rep.get("before")))
        if not rep.get("unitsPatched"):
            print("  ATTENTION : AUCUNE entree BC.Units patchee -- le montage est MUET")
    elif montage.startswith("mawclaws"):
        rep = CI.equip_relic(bc, MC_OWNER, "MawClawsOfThyrax", 1)
        print("  relique posee : %s -> %s (id %s), %d entree(s) patchee(s), config ajoutee=%s"
              % (rep["unitId"], rep["ability"], rep["abilityId"], rep["unitsPatched"],
                 rep["configAdded"]))
        if not rep["unitsPatched"]:
            print("  ATTENTION : AUCUNE entree BC.Units patchee -- le montage est MUET")
        if montage == "mawclaws":
            # le gate porte sur le MOVER : `HasTrait(case.unit, Summon)`. Aucune unite du pool ne
            # porte `Summon` -> on l'ACCORDE, ce qui est exactement le substrat qu'interroge
            # `HasTrait` (kit + traits accordes en bataille).
            rt = CI.add_unit_trait(bc, MC_MOVER, "Summon")
            print("  trait accorde : %s -> Summon, avant=%s apres=%s"
                  % (MC_MOVER, rt.get("before"), rt.get("after")))
    else:
        rep = CI.graft_passive_ability(bc, owner, "HaywireMine")
        print("  greffe : %s -> HaywireMine (id %s), %s entree(s) patchee(s), avant=%s"
              % (owner, rep.get("abilityId"), rep.get("unitsPatched"), rep.get("before")))
        if not rep.get("unitsPatched"):
            print("  ATTENTION : AUCUNE entree BC.Units patchee -- le montage est MUET")

    # CONFOND -- une relique du SEED non desiree fausserait la mesure sans rien dire (c'est ce qui
    # a rendu #477-r31 rouge). On l'IMPRIME pour toutes les unites du montage.
    etat = CI.relic_state_of_seed_bc(bc)
    concernes = {mover, owner, "necroWarden", "orksNob"}
    for uid, rel in sorted((etat or {}).items()):
        if uid in concernes:
            print("  relique de seed : %-24s -> %s" % (uid, rel))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bc), encoding="utf-8")
    return out_path


def _build(seed, board, montage, seed_bc: Path, state: Path):
    extra = build_extra(board, montage)
    extra[1] = str(seed_bc)
    argv = ([sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
             "--state-file", str(state)] + extra)
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:\n%s" % ((p.stderr or p.stdout or "")[-2500:]))
        return None
    print((p.stdout or "").strip()[-700:])
    return json.loads(state.read_text())["runnerId"]


# ---- les modeles confrontes ------------------------------------------------------------------
def _owners_adj(tile, lc, ability_id: int, camp: str) -> int:
    """Porteurs de `ability_id` du camp `camp` ADJACENTS a `tile` (adjacence NATIVE)."""
    from engine import battle_query as bq
    elev, neigh = lc.get("elev_by_pos"), bq.neigh_map(lc)
    src = lc.get("friend_units") if camp == "ami" else lc.get("enemy_units")
    return sum(1 for u in (src or ())
               if u.get("pos") and bq.are_entities_adjacent(tile, tuple(u["pos"]), elev, neigh)
               and int(ability_id) in (u.get("triggered") or ()))


def _owners_any(lc, ability_id: int, camp: str) -> int:
    """Porteurs de `ability_id` du camp `camp` SUR LE PLATEAU, sans condition de tuile.

    Pour un corps qui ne lit PAS la position du porteur (`HaywireMine`), le dispatcher somme le
    terme UNE FOIS PAR PORTEUR retenu par le pre-gate : c'est ce compte-la, pas la proximite."""
    src = lc.get("friend_units") if camp == "ami" else lc.get("enemy_units")
    return sum(1 for u in (src or ()) if int(ability_id) in (u.get("triggered") or ()))


def _models(tile, leaves, lc, wt, montage) -> tuple:
    """Le terme rendu par CHAQUE modele -- le port (lu dans son VRAI foyer) et ses mutants.

    Chaque mutant DECLARE ce qu'il observe :
      * `CAMP-DEUX`   : le pre-gate `IsFriend` d'`IterateAbilities` n'existerait pas -> les porteurs
                        ENNEMIS compteraient aussi ;
      * `CAMP-ENNEMI` : le camp serait inverse ;
      * `SANS-GATE`   : le gate du corps (faction / trait Summon / identite de la mine) serait absent ;
      * `COUNT (x n)` : le terme s'ajouterait une fois par porteur ADJACENT (le natif ne le fait pas
                        pour un corps qui lit l'adjacence : un seul `yield` par paire) ;
      * `ABSENT`      : l'etat du port AVANT cette tranche.
    """
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    from engine.entities.unit_faction import UnitFaction
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.utilities.utility_type import UtilityType
    from engine import battle_query as bq                        # noqa: F401
    from engine.entities.tile_extensions import get_steppable_unit
    from engine.playbook.non_owner import (MawClawsOfThyraxNonOwnerPlaybook as MC,
                                           PurgeResponseNonOwnerPlaybook as PR,
                                           HaywireMineNonOwnerPlaybook as HM)

    tile = (tile[0], tile[1])
    porte = float(leaves.get(int(UtilityType.TriggeredAbilitiesNonOwner), 0.0))

    if montage.startswith("purge"):
        aid, key = int(T.PurgeResponse), PR.KEY
        fac = lc.get("unit_faction")
        gate = fac is not None and int(fac) == int(UnitFaction.LeaguesOfVotann)
        na, ne = _owners_adj(tile, lc, aid, "ami"), _owners_adj(tile, lc, aid, "ennemi")
    elif montage.startswith("mawclaws"):
        aid, key = int(T.MawClawsOfThyrax), MC.KEY
        gate = int(UnitTrait.Summon) in {int(t) for t in (lc.get("unit_traits") or ())}
        na, ne = _owners_adj(tile, lc, aid, "ami"), _owners_adj(tile, lc, aid, "ennemi")
    else:
        aid, key = int(T.HaywireMine), HM.KEY_FRIENDLY
        occ = get_steppable_unit(tile, lc)
        vis = (occ or {}).get("vis")
        gate = bool(vis and str(vis).split(":")[0] in HM().mine_unit_ids())
        steppable = occ is not None
        # le corps ne lit PAS la position du porteur -> tous les porteurs du camp comptent.
        na, ne = _owners_any(lc, aid, "ami"), _owners_any(lc, aid, "ennemi")
        # ⚠ 1531 est la SEULE classe a `SLOT_4 = True` : les porteurs ENNEMIS sont yieldes AUSSI,
        # avec l'autre cle (-30). Ses mutants ne portent donc PAS sur les memes axes que ceux des
        # deux autres montages, et les ecrire comme eux serait un modele FAUX.
        we = float(wt.sub("TriggeredAbilitiesNonOwner", HM.KEY_ENEMY))
        wa = float(wt.sub("TriggeredAbilitiesNonOwner", HM.KEY_FRIENDLY))
        mods = {
            "PORT":        porte,
            # le pre-gate `<slot 4>` n'existerait pas -> les ennemis seraient ECARTES et la branche
            # -30 deviendrait morte. C'est EXACTEMENT l'etat du port avant la mesure live.
            "SLOT4-OFF":   float(wa * na) if gate else 0.0,
            # les deux camps verseraient la MEME cle (-50), c.-a-d. le corps sans son `IsFriend`.
            "UNE-SEULE-CLE": float(wa * (na + ne)) if gate else 0.0,
            # les cles seraient INVERSEES (ami <-> ennemi).
            "CLES-INVERSEES": float(we * na + wa * ne) if gate else 0.0,
            # le gate `HasUnitId` serait absent : tout occupant steppable armerait le terme.
            "SANS-GATE":   float(wa * na + we * ne) if steppable else 0.0,
            "ABSENT":      0.0,
        }
        return mods, {"na": na, "ne": ne, "gate": bool(gate), "w": wa,
                      "steppable": bool(steppable)}

    # Corps qui lisent l'ADJACENCE au porteur : le natif yielde une paire par porteur retenu, et
    # le corps ne verse qu'une fois par paire -- donc `x n` ne se distingue de `x 1` que si DEUX
    # porteurs du meme camp sont adjacents a la meme tuile. C'est dit, pas suppose.
    w = float(wt.sub("TriggeredAbilitiesNonOwner", key))
    mods = {
        "PORT":        porte,
        "CAMP-DEUX":   float(w * (1 if (gate and (na + ne)) else 0)),
        "CAMP-ENNEMI": float(w * (1 if (gate and ne) else 0)),
        "SANS-GATE":   float(w * (1 if na else 0)),
        "COUNT (x n)": float(w * na) if gate else 0.0,
        "ABSENT":      0.0,
    }
    return mods, {"na": na, "ne": ne, "gate": bool(gate), "w": w, "steppable": False}


def _bras(prof, tiles, montage):
    """Les DEUX regimes que le pas doit couvrir pour etre DISCRIMINANT -- et ils ne sont PAS les
    memes selon l'axe du gate.

    * `purge` / `mawclaws` : le gate porte sur le MOVER, le terme sur l'ADJACENCE au porteur. Le
      discriminant est donc le CAMP du porteur adjacent : bras AMI (le terme tombe) contre bras
      ENNEMI (le pre-gate `IsFriend` l'ecarte). Sans les deux, `CAMP-DEUX` ne separe rien.
    * `haywire` : le gate porte sur l'OCCUPANT DE LA TUILE et le corps ne lit PAS la position du
      porteur -- `na`/`ne` sont donc CONSTANTS sur toute la decision, et le critere « bras AMI seul
      vs bras ENNEMI seul » est structurellement VIDE. Mesure : 4 activations, `bras AMI=0
      ENNEMI=0` a chaque fois. Le discriminant y est la TUILE : celle qui porte le steppable contre
      les autres. `haywire` exige la MINE (gate vrai) ; `haywire-gate` exige un steppable qui n'est
      PAS la mine (gate faux mais occupant present), sans quoi `SANS-GATE` serait inerte et le
      controle ne controlerait rien."""
    if montage == "haywire":
        return ([t for t in tiles if prof[t]["gate"]],
                [t for t in tiles if not prof[t]["gate"]])
    if montage == "haywire-gate":
        # ⚠ MESURE : la greffe de `HaywireMine` fait SPAWNER la mine en bataille (c'est ce que
        # l'ability fait), des DEUX cotes -- 4 mines pour UNE posee a la main. Un controle
        # « aucune mine sur le plateau » est donc IMPOSSIBLE par ce montage, et le premier essaye
        # a rendu ROUGE en croyant mesurer le decoy alors qu'il mesurait une mine spawnee.
        # Le controle porte donc sur la TUILE : celle qui porte un steppable qui N'EST PAS la mine
        # (le decoy `genesSmnDecoy`) -- c'est la, et seulement la, que `HasUnitId` doit couper.
        return ([t for t in tiles if prof[t]["steppable"] and not prof[t]["gate"]],
                [t for t in tiles if not prof[t]["steppable"]])
    return ([t for t in tiles if prof[t]["na"] > 0 and prof[t]["ne"] == 0],
            [t for t in tiles if prof[t]["ne"] > 0 and prof[t]["na"] == 0])


def mesurer(call, rid, montage="purge", max_steps=25, trace=print) -> dict:
    """Marche la trajectoire NATIVE jusqu'au pas ou les DEUX bras sont HOOKES, arme les hooks pour
    UN SEUL `aiStepDryRun`, et rend la mesure.

    ⚠ `scorerDamageTraceOn/Off` acceptent desormais un `runnerId` (#483) : on le PASSE, ce qui
    rend le `*Off` d'un autre agent inoffensif pour cette capture. Sans lui, le comportement est
    session-global et deux probes de cette famille joues en parallele se coupent l'un l'autre."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene

    carrier = _mover(montage)
    dv0 = call("decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    cid = next((u.get("id") for u in (dv0.get("units") or [])
                if u.get("visualId") == carrier and u.get("ctrl")), None)
    trace("  carrier u%s (%s)" % (cid, carrier))
    if cid is None:
        return {"erreur": "carrier %s absent de la bataille" % carrier}

    step, seen = 0, 0
    while step < max_steps:
        dry = call("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            return {"erreur": "trajectoire native epuisee au pas %d (%s) apres %d activation(s)"
                              % (step, dry.get("error"), seen)}
        if dry.get("activatedUnitId") != cid:
            _apply_native_via(call, rid, dry)
            step += 1
            continue
        seen += 1
        dv = call("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = call("aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        wt = W.load()
        pred = _scene.build_predictor(call, rid)
        ctx = _ai_ctx.build(call, rid, dv, mov_by_unit, cid, wt, pred)
        tiles = list(ctx.action_tiles or [])
        prof = {}
        for t in tiles:
            leaves, lc = _port_leaves(ctx, t)
            prof[t] = _models(t, leaves, lc, wt, montage)[1]
        ba, bb = _bras(prof, tiles, montage)
        trace("  pas %-3d activation #%d : %d candidates | bras AMI=%d bras ENNEMI=%d"
              % (step, seen, len(tiles), len(ba), len(bb)))
        if not (ba and bb):
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        call("scorerDamageTraceOn", {"runnerId": rid}, 90)
        call("scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
        try:
            call("aiStepDryRun", {"runnerId": rid}, 90)
            tterm = call("scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
            elev = call("scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
            leaf = call("scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
        finally:
            call("scorerDamageTraceOff", {"runnerId": rid}, 60)

        tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
        el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
        te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                      "col", "row", "value")
        if not tt:
            trace("  aucun event tileTerm a ce pas -- on continue la marche")
            _apply_native_via(call, rid, dry)
            step += 1
            continue
        hooked = [t for t in tiles if t in tt]
        ha, hb = _bras(prof, hooked, montage)
        trace("  tuiles HOOKEES=%d | bras AMI=%d bras ENNEMI=%d" % (len(hooked), len(ha), len(hb)))
        if not (ha and hb):
            trace("  les hooks n'ont pas couvert les DEUX bras -- on continue la marche")
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        rows = []
        for t in sorted(hooked):
            vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
            leaves, lc = _port_leaves(ctx, t)
            mods, p = _models(t, leaves, lc, wt, montage)
            x = (vt - ve - vf) if None not in (vt, ve, vf) else None
            rows.append({"tile": t, "x_nat": x, "x_port": x_port(leaves), "models": mods,
                         "na": p["na"], "ne": p["ne"], "gate": p["gate"],
                         "steppable": p.get("steppable", False),
                         "tile7": vt, "elev": ve, "tile_eff": vf,
                         "leaves": {k: v for k, v in leaves.items() if abs(v) > 1e-9}})
        _l0 = _port_leaves(ctx, tiles[0])[1]
        return {"rows": rows, "prof": prof, "step": step, "uid": cid, "montage": montage,
                "bras_a": ha, "bras_b": hb,
                "friend_units": list(_l0.get("friend_units") or ()),
                "enemy_units": list(_l0.get("enemy_units") or ())}

    return {"erreur": "aucun pas DISCRIMINANT en %d pas (%d activations du carrier)"
                      % (max_steps, seen)}


def divergences(rows) -> dict:
    out = {}
    for nom in (rows[0]["models"] if rows else {}):
        n = 0
        for r in rows:
            if r["x_nat"] is None:
                continue
            xm = r["x_port"] - r["models"]["PORT"] + r["models"][nom]
            if abs(r["x_nat"] - xm) > 1e-6:
                n += 1
        out[nom] = n
    return out


def run(call, rid, montage="purge", max_steps=25) -> int:
    mes = mesurer(call, rid, montage, max_steps)
    if mes.get("erreur"):
        print("  ROUGE : %s" % mes["erreur"])
        return 1
    rows = mes["rows"]
    print("\n  tuile      nA nE gate | Tile7nat  Elev  TileEff  X_nat  | X_port  DELTA")
    bad = 0
    for r in rows:
        d = (r["x_nat"] - r["x_port"]) if r["x_nat"] is not None else None
        if d is not None and abs(d) > 1e-6:
            bad += 1
        print("  %-10s %2d %2d %4s | %-9s %-5s %-8s %-6s | %-7.4g %s"
              % (r["tile"], r["na"], r["ne"], r["gate"], r["tile7"], r["elev"], r["tile_eff"],
                 r["x_nat"], r["x_port"], ("%.4g" % d) if d is not None else "?"))

    if bad:
        from engine.utilities.utility_type import UtilityType
        print("\n  VENTILATION du port sur les tuiles en DESACCORD (feuilles non nulles) :")
        for r in rows:
            d = (r["x_nat"] - r["x_port"]) if r["x_nat"] is not None else None
            if d is None or abs(d) <= 1e-6:
                continue
            noms = []
            for k, v in sorted(r["leaves"].items()):
                try:
                    noms.append("%s=%g" % (UtilityType(k).name, v))
                except ValueError:
                    noms.append("<%d>=%g" % (k, v))
            print("    %-10s manque %+.4g | %s" % (r["tile"], d, ", ".join(noms) or "(aucune)"))
        print("  VOISINS vus par le port (pos / triggered / traits) :")
        for camp, us in (("ami", mes.get("friend_units") or ()),
                         ("ennemi", mes.get("enemy_units") or ())):
            for u in us:
                print("    %-6s %-24s @%-8s trg=%s traits=%s"
                      % (camp, u.get("vis"), u.get("pos"), list(u.get("triggered") or ()),
                         list(u.get("traits") or ())[:6]))

    mordu = divergences(rows)
    print("\n  CONTRE-EPREUVE (X_nat vs X_<modele>, sur les %d tuiles hookees) :" % len(rows))
    for nom, n in mordu.items():
        print("    %-14s divergences = %d / %d   a_mordu=%s"
              % (nom, n, len(rows), "OUI" if n else "NON"))

    rc = 0
    if bad:
        print("\n  ACCORD : ROUGE -- %d tuile(s) en desaccord X_nat vs X_port sur %d"
              % (bad, len(rows)))
        rc = 1
    else:
        print("\n  ACCORD : VERT -- 0 desaccord X_nat vs X_port sur %d tuiles" % len(rows))

    sep = MUTANT_SEPARATEUR[montage]
    if not mordu.get(sep):
        print("  SEPARATION : ROUGE -- le mutant %r rend la MEME chose que le port sur ce "
              "montage : REGIME DEGENERE, rien n'est tranche" % sep)
        rc = 1
    else:
        print("  SEPARATION : VERT -- le mutant %r diverge du natif sur %d tuile(s)"
              % (sep, mordu[sep]))

    if montage in MONTAGES_GATE_COUPE:
        inertes = [m for m in mordu if m not in ("SANS-GATE", "PORT")]
        gate_actif = any(r["gate"] for r in rows)
        actifs = [m for m in inertes if mordu.get(m)]
        if gate_actif or actifs:
            print("  GATE : le gate a PASSE (gate=%s) ou un mutant declare INERTE a mordu (%s) -- "
                  "l'inertie declaree est FAUSSE" % (gate_actif, ", ".join(actifs) or "-"))
            rc = 1
        else:
            print("  GATE : INERTE PAR ALGEBRE (le mover/la tuile ne franchit pas le gate) -- %s ne"
                  " peuvent PAS mordre, et c'est ASSERTIONNE ; seul `SANS-GATE` separe ici"
                  % ", ".join(sorted(inertes)))
    else:
        if montage == "haywire-gate":
            # le CONTROLE : sur la tuile qui porte un steppable NON-mine, le gate `HasUnitId` doit
            # couper et le terme natif doit valoir 0. Assertionne DANS LES DEUX SENS -- si aucune
            # telle tuile n'est hookee, le controle n'a rien controle et c'est un ROUGE.
            ctrl = [r for r in rows if r["steppable"] and not r["gate"]]
            if not ctrl:
                print("  GATE : ROUGE -- aucune tuile hookee ne porte un steppable NON-mine : le "
                      "controle du gate `HasUnitId` n'a rien exerce")
                rc = 1
            else:
                print("  GATE : %d tuile(s) portent un steppable NON-mine ; le gate y COUPE "
                      "(assertionne) -- c'est `SANS-GATE` qui les separe" % len(ctrl))
        elif not all(r["gate"] for r in rows):
            n_ok = sum(1 for r in rows if r["gate"])
            if montage.startswith("haywire"):
                # ATTENDU ici : le gate de 1531 porte sur la TUILE (l'occupant), pas sur le mover --
                # il ne peut donc passer que sur la tuile MINEE. On exige >= 1, pas « toutes ».
                if not n_ok:
                    print("  GATE : ROUGE -- AUCUNE tuile hookee ne porte la mine : le montage ne "
                          "mesure pas ce qu'il annonce")
                    rc = 1
                else:
                    print("  GATE : PASSE sur %d des %d tuiles -- ATTENDU pour 1531, dont le gate "
                          "porte sur l'OCCUPANT de la tuile et non sur le mover" % (n_ok, len(rows)))
            else:
                print("  GATE : ROUGE -- le gate ne passe que sur %d des %d tuiles alors que le "
                      "mover devrait le franchir partout" % (n_ok, len(rows)))
                rc = 1
        else:
            print("  GATE : PASSE sur les %d tuiles (assertionne)" % len(rows))
        for m in sorted(mordu):
            if m in ("PORT", "ABSENT", MUTANT_SEPARATEUR[montage]) or mordu.get(m):
                continue
            print("  NON SEPARE ICI : le mutant %r rend la MEME chose que le port sur ce montage "
                  "-- son axe n'y est pas exerce, et le taire le ferait passer pour confirme." % m)
    print("  VERDICT : %s" % ("ROUGE" if rc else "VERT"))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--montage", default="purge", choices=MONTAGES)
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()

    rc0, rec = step0()
    rc0 |= step0b(rec["build"])
    rc0 |= step0c()
    if a.offline_only:
        print("\nVERDICT OFFLINE : %s" % ("ROUGE" if rc0 else "VERT"))
        return rc0

    try:
        _exiger_build_des_rva()
    except BuildPinRefused as e:
        print("REFUS build_pin : %s" % e)
        return 2

    sid = _resolve_session()
    call = (lambda m, b, t=90: _r(sid, m, b, t))          # noqa: E731
    # ⚠ OBLIGATOIRE dans tout montage qui GREFFE (#448-r3-r1-r1) : sans transport ambiant lie,
    # `load_state` ne seede pas `UnitContext.*_abilities` et le port retombe sur le gameconfig, qui
    # ne porte PAS la greffe. Le terme mesure serait alors nul cote PORT et l'accord se lirait comme
    # un desaccord -- ou pire, une assertion NEGATIVE passerait a vide, en VERT. Deux des trois
    # montages de ce cas greffent (`purge`, `haywire`).
    bind_ambient_rpc(sid)
    rid = a.runner
    tmp = None
    if rid is None:
        state = Path(a.state_file) if a.state_file else \
            (ROOT / "logs" / ("477r35-%s.json" % uuid.uuid4().hex[:8]))
        seed_bc = _seed_bc_montage(state.with_suffix(".bc.json"), a.montage)
        print("\n[1] montage %r / board %s / seed %s" % (a.montage, a.board, a.seed))
        rid = _build(a.seed, a.board, a.montage, seed_bc, state)
        tmp = rid
        if rid is None:
            return 1
    print("  runner %s" % rid)
    try:
        return run(call, rid, a.montage, a.max_steps) | rc0
    finally:
        if tmp is not None:
            try:
                call("disposeRunner", {"runnerId": tmp}, 30)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
