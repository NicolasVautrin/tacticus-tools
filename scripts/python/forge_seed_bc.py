#!/usr/bin/env python
"""forge_seed_bc - REGENERE `data/seed-bc.json` par la FABRIQUE NATIVE du jeu.

Sans bataille, sans capture, sans un octet vers le serveur.

CE QUE CA RESOUT
----------------
`data/seed-bc.json` etait une PHOTO : la capture d'UNE bataille reelle. Deux
consequences, toutes deux mesurees :

  * son `Units[]` ne porte que les unites presentes ce jour-la -- 175 sur 683
    possibles. D'ou `catalog_inject`, qui injecte au coup par coup les porteurs
    manquants, et dont l'ecart se creuse a chaque MAJ du jeu EN SILENCE (la
    docstring de `catalog_inject` annoncait 17 unites manquantes, la re-mesure
    du 2026-08-15 en a trouve 21) ;
  * le REGENERER exigeait d'ETRE EN BATAILLE. `dump_boards.py` sait le
    (re)capturer, mais par `dumpBattleConfig` -> `getLiveBattleConfig`, qui rend
    `{ok: false, err: "no live BC"}` hors combat -- MESURE le 2026-08-19, jeu au
    meta. Perdre le fichier coutait donc une bataille (stamina / jeton).

LA VOIE EST NATIVE, ET C'EST LE POINT
--------------------------------------
`Idun.Source.IdunBattle.View.BattleConfigBuilder` est une FABRIQUE PURE : montee
de toutes pieces (`BattleConfigGameConfigValues` + le builder, exactement comme
`...GameModeSource$$LoadBattleInternal` la monte), elle rend une
`BattleConfiguration` complete. On ne detourne rien : on appelle ce que le jeu
appelle. Le montage vit deja dans le RPC `guildWarBuildBc`
(`frida/hooks/features/guild-war-config.ts`).

LE LEVIER EST `availableMainPlayerUnits`, PAS LE MODE DE JEU
-------------------------------------------------------------
`BC.Units` est assemble par trois adders qui convergent tous sur une seule
fabrique, `BattleConfigBuilder$$GetUnitConfiguration(unitModel, values, hp)` :

  * `AddMainPlayerUnitConfigs`  <- enumere l'`IUnitProgression` qu'on donne
  * `AddPredefinedUnitConfigs`  <- les ennemis passes en `opponentLineup`
  * `AddSummonUnitConfigs`      <- les summons, SANS CONDITION

Aucun mode de jeu ne rend les trois populations : les npc n'entrent jamais
autrement que comme ennemis de CETTE bataille-la. Mais en passant TOUT le
gameconfig aux deux premiers, le builder produit le catalogue exhaustif.
MESURE le 2026-08-19 : `Units` = 683 -- lineup 127/127, summons 65/65,
npc 491/491, ~1,1 Mo, jeu vivant apres coup.

FIDELITE : 23 SECTIONS SUR 23
------------------------------
La BC forgee a ete confrontee au seed capture section par section. Identiques au
bit pres : `Damage`, `Effect`, `Targeting`, `Victory`, `Score`, `Turn`,
`UnitProgression`, `EnvironmentAbilities`, `UnitSpawningOverTime`,
`DefaultActiveAbility`, `AbilitiesToHide`, `RuleSet`, `SpawnPointSetIndex`,
`GameMode` et les 8 drapeaux -- plus `Board` et `Tiles` (qui viennent donc de
l'`IdunUniverse`, pas d'une capture). `Player` ne differe que par le NOM de
l'ennemi (`enemy` / `enemy_1`). Les seuls ecarts de fond etaient des parametres
de MODE, ramenes par `_semantique_campagne`.

⚠ ET LA CAPTURE N'EST PAS UN ARBITRE -- ELLE EST LE PARTI PERIME.
Le seul ecart de catalogue constate entre forge et capture etait une attribution
MORTE, pas un manque de la forge. Mesure :

    gameconfig VIVANT : necroOverlord.passiveAbilities = ["MyWillBeDoneOverlord"]
    forge  : necroOverlord.PassiveAbilities = [1556]  (MyWillBeDoneOverlord)
    capture: necroOverlord.PassiveAbilities = [1045]  (MartialApotheosis)

Le referentiel du montage est `BC.Units[].PassiveAbilities`, lu par
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` (`config+0xa8`)
puis `TriggeredAbilityComponent$$TryAdd(id, state, 2)` -- etabli par
`probe_392_martial_apotheosis_bc_carrier.py`, qui a REFUTE le « 0 porteur » de
`probe_354_*`. Le jeu n'accorde PLUS 1045 a `necroOverlord`.

⛔ NE JAMAIS COMBLER UN ECART DEPUIS L'ANCIENNE CAPTURE. Une premiere version de ce
module recopiait les configs manquantes ; c'etait deux fautes en une -- faire
dependre la forge de l'artefact qu'elle remplace, et REIMPORTER la peremption
qu'elle existe pour supprimer. Ce qui arbitre, c'est le gameconfig VIVANT et le
decompile. Si un ecart apparaissait dans l'AUTRE sens (une config que la forge ne
sait pas poser), la voie generique est native et sans argument, sur la progression
REELLE -- `UnitProgression$$LoadAllGloballyConfiguredTraitConfigs` et
`...$$LoadAllGloballyConfiguredPassiveAbilityConfigs` -- jamais une recopie.

USAGE (depuis scripts/python) :
    python forge_seed_bc.py                          # ecrit data/seed-bc.json
    python forge_seed_bc.py --out ../../logs/f.json  # ecrit ailleurs
    python forge_seed_bc.py --diff A.json B.json     # compare deux BC, sans forger

Voir aussi `dump_boards.py` (geometrie des boards + capture historique du seed).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import gameconfig as G
import rl_collect_batch as R

# Board du template. Celui du seed historique (`Campaign1_74`), garde pour que le
# fichier forge soit un REMPLACANT DIRECT. `buildNormalizedBC` swappe le board de
# toute facon : ce choix n'engage que l'allure du template au repos.
BOARD_TEMPLATE = "C1_74"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _semantique_campagne(bc: dict) -> list[str]:
    """Ramene les TROIS champs de MODE a la semantique campagne. Rend les touches.

    POURQUOI CEUX-LA, ET PAS UN DE PLUS. Ce sont les seuls ecarts mesures entre la
    BC forgee et une capture de campagne ; ils viennent de la porte par laquelle on
    appelle le builder (guild war), pas d'un manque de la fabrique. Toute reecriture
    supplementaire serait du maquillage d'une sortie native -- et le maquillage est
    precisement ce qui rend un template inverifiable.
    """
    touches = []
    if bc.get("GameMode") != "Campaign":
        bc["GameMode"] = "Campaign"
        touches.append("GameMode")
    d = bc.get("Damage")
    if isinstance(d, dict) and d.get("IgnoreDamageSpread") is not False:
        # Regle de guild war ; la campagne applique le damage spread.
        d["IgnoreDamageSpread"] = False
        touches.append("Damage.IgnoreDamageSpread")
    v = bc.get("Victory")
    attendu = {"MainPlayerHasNoHeroesAndSummons": 1, "KillAllEnemyUnits": 1}
    if isinstance(v, dict) and v.get("VictoryConditions") != attendu:
        v["VictoryConditions"] = dict(attendu)
        touches.append("Victory.VictoryConditions")
    return touches


def npc_avec_progression() -> list[str]:
    """Les ids `units.npc`, suffixes de leur `ProgressionIndex` MAX -- SAUF quand il vaut 0.

    ⚠ SUFFIXER `:0` FAIT LEVER LE BUILDER, et c'est ce qui a fait croire que certaines
    unites n'etaient pas montables. Mesure du 2026-08-19, sur le meme lot :

        les 14 `powup*` avec `:0`  -> `GetGuildWarsConfig` LEVE (« system error »)
        les 14 `powup*` NUS        -> OK, et `powupDamage` sort `PassiveAbilities: [1139]`
                                      -- exactement ce que le mirror offline synthetise

    Un suffixe `:0` n'apporte donc RIEN (l'index 0 est deja le defaut) et casse. Le
    diagnostic « ces unites ne sont pas montables » etait FAUX : c'est la forme de l'id
    qu'on leur donnait qui l'etait. L'enjeu est concret -- un power-up sans son passif
    est INERTE au ramassage, et `probe_10004_powerup_spawn_live.py` avertit que sans son
    entree au catalogue « la fabrique ne construit rien, SANS LA MOINDRE ERREUR ».

    Le suffixe n'etait pas « ignore » : `UnitProgression$$GetUnit(String)`, auquel le
    delegue etait lie, ne REGARDE jamais le dictionnaire npc -- il interroge le cache
    des heros et fabrique un `CachedUnitModel` sur echec. D'ou Health 0 / Level 1 /
    Rank 0 sur les 491 npc, sans la moindre erreur. Corrige par `enemyResolver: "npc"`
    (cf. `forger`), qui vise `GetNpcUnit(String)`.
    """
    cfg = json.loads(G._find_gameconfig().read_text(encoding="utf-8"))
    cfg = cfg.get("clientGameConfig") or cfg
    npc = cfg["units"]["npc"]
    out = []
    for uid in sorted(npc):
        rows = (npc[uid] or {}).get("stats") or []
        idxs = [r.get("ProgressionIndex") for r in rows
                if isinstance(r, dict) and isinstance(r.get("ProgressionIndex"), int)]
        n = max(idxs) if idxs else 0
        out.append(f"{uid}:{n}" if n > 0 else uid)
    return out


def _construire(sid: int, board: str, lineup: list[str], npcs: list[str]) -> dict | str:
    """Un appel au builder. Rend la BC, ou le message d'erreur du natif."""
    ennemis = [{"UnitId": n, "RemainingHealth": None, "MaxHealth": None} for n in npcs]
    res = _unwrap(R._rpc(sid, "guildWarBuildBc", [{
        "id": "ForgedTemplate",
        "boardId": board,
        "spawnPointsSet": 0,
        "enemyLineupJson": json.dumps(ennemis),
        "playerUnits": lineup,
        # `hero` (le defaut du RPC) lie le delegue a `UnitProgression$$GetUnit(String)`, qui
        # interroge le cache des HEROS et fabrique un `CachedUnitModel` sur echec : un id npc
        # en ressort a Health 0 / Level 1 / Rank 0, SANS erreur. `npc` vise
        # `GetNpcUnit(String)` -- la branche ou `GetUnitOfAnyKind(id, stripLevel: true)`
        # aboutit, et c'est cette derniere que la lambda du jeu appelle.
        "enemyResolver": "npc",
    }], timeout=300))
    if isinstance(res, dict) and res.get("ok") and res.get("configJson"):
        return json.loads(res["configJson"])
    return str(res)[:300]


def _bisecter(sid: int, board: str, lineup: list[str], npcs: list[str]) -> list[str]:
    """Les ids qui, SEULS, font lever le builder. Bisection -- rien de suppose.

    POURQUOI DERIVER PLUTOT QUE FIGER. Mesure du 2026-08-19 : 25 des 491 npc font lever
    `GetGuildWarsConfig` (« system error »), et ils forment des familles qu'on aurait pu
    croire devinables -- 14 `powup*` (power-ups de TERRAIN, poses par le board et non par
    une unite), 4 unites de tutoriel (`*Tut*` / `FTUEtest`), 2 `LootObj`, 2 leurres. Mais
    la devinette AURAIT ETE FAUSSE DANS LES DEUX SENS : seuls 2 des 31 `LootObj` fautent,
    et trois vrais npc en font partie (`admecBossBelisarius`, `eldarBossMauganRaUltra`,
    `ultraNpc3Intercessor`). Une liste en dur serait donc a la fois trop large et trop
    etroite -- et elle pourrirait au prochain build. On la re-derive, et seulement quand
    le lot complet a echoue : le cout (une centaine d'appels) n'est paye qu'en panne.
    """
    if not npcs:
        return []
    if isinstance(_construire(sid, board, lineup, npcs), dict):
        return []
    if len(npcs) == 1:
        return list(npcs)
    m = len(npcs) // 2
    return (_bisecter(sid, board, lineup, npcs[:m])
            + _bisecter(sid, board, lineup, npcs[m:]))


def forger(sid: int, board: str = BOARD_TEMPLATE) -> tuple[dict, dict]:
    """Forge la BC par la fabrique native. Rend `(bc, bilan)`. N'ECRIT RIEN.

    L'`IdunUniverse` est desormais posee PAR L'AMORCE (`autoBootExtraire` publie
    `idunUniverse` / `idunUniverseVia`). L'appel a `tryGlobalsCapture` ci-dessous est
    garde comme repli IDEMPOTENT : il sert le cas `--no-amorce` et une session plus
    ancienne que ce correctif. Il rend « already captured » quand il n'y a rien a faire.

    ⚠ LA PROGRESSION DES ENTREES SUIT CE QU'ON PASSE, et trois zeros sont ATTENDUS,
    dont DEUX sont CORRECTS -- les confondre avec un echec ferait renoncer a une
    regeneration juste :
      * 65 summons a stats nulles : CORRECT, elles derivent de leur invocateur ; une
        capture reelle montre exactement le meme profil ;
      * 11 MoW : table de progression separee (`heroProgressionStepsMoW`) ;
      * les 21 unites NON POSSEDEES sortent a Rank 0, les npc a l'index 0 (cf.
        `npc_avec_progression`). La normalisation au rang cible reste la passe qui
        existe deja (`buildNormalizedBC` / `catalog_inject --rank`).
    """
    u = _unwrap(R._rpc(sid, "tryGlobalsCapture", [], timeout=30))
    if not (isinstance(u, dict) and u.get("ok")):
        raise RuntimeError(
            "`IdunUniverse` non capture et `tryGlobalsCapture` a echoue : "
            f"{str(u)[:200]} -- la forge ne peut pas monter le builder")

    lineup = sorted(G._index()["lineup"])
    npcs = npc_avec_progression()

    sortie = _construire(sid, board, lineup, npcs)
    ecartes: list[str] = []
    if not isinstance(sortie, dict):
        # Le lot complet a leve. On DERIVE les fautifs plutot que d'abandonner -- et on ne
        # les tait pas : un catalogue ampute qui ne dit pas ce qu'il a perdu se lit comme
        # complet, et c'est exactement la faute que ce module combat.
        ecartes = _bisecter(sid, board, lineup, npcs)
        if not ecartes:
            raise RuntimeError(f"guildWarBuildBc KO sans fautif isolable : {sortie}")
        gardes = [n for n in npcs if n not in set(ecartes)]
        sortie = _construire(sid, board, lineup, gardes)
        if not isinstance(sortie, dict):
            raise RuntimeError(
                f"guildWarBuildBc KO meme apres retrait de {len(ecartes)} npc : {sortie}")

    bc = sortie
    touches = _semantique_campagne(bc)

    idx = G._index()
    ids = {x["Id"].split(":")[0] for x in bc.get("Units", [])}
    bilan = {
        "units": len(bc.get("Units", [])),
        "lineup": f"{len(ids & set(idx['lineup']))}/{len(idx['lineup'])}",
        "summons": f"{len(ids & set(idx['summons']))}/{len(idx['summons'])}",
        "npc": f"{len(ids & set(idx['npc']))}/{len(idx['npc'])}",
        "board": board,
        "ramenes_a_la_campagne": touches,
        "npc_ecartes": ecartes,
    }
    return bc, bilan


# Sections dont l'egalite est le CRITERE de fidelite d'une forge a une autre BC.
# `Units`, `Abilities`, `Utilities`, `Board`, `PredefinedUnits` et `Player` en sont
# ECARTES A DESSEIN : ce sont precisement les sections qu'une forge doit faire
# DIFFERER d'une capture (catalogue exhaustif, board choisi, pas d'ennemis pre-poses).
SECTIONS_DE_FIDELITE = (
    "Damage", "Effect", "Targeting", "Victory", "Score", "Turn", "UnitProgression",
    "EnvironmentAbilities", "UnitSpawningOverTime", "DefaultActiveAbility",
    "AbilitiesToHide", "UseGroupForAddUnit", "NoAutomaticUnitTurns",
    "EnableIdunAbilities", "IsTestBattle", "DisableTimeouts",
    "DisableAnimatorRecovery", "DisableActiveAbilitiesOnAI", "DisableRandomness",
    "RandomizeAiInput", "SpawnPointSetIndex", "RuleSet", "GameMode",
)


def diff(a: dict, b: dict) -> int:
    """Compare deux BC. Rend le nombre de sections de fidelite DIVERGENTES.

    ⚠ AUCUN des deux cotes n'est un arbitre. Une divergence DESIGNE un endroit ou
    regarder ; ce qui tranche est le gameconfig VIVANT et le decompile. Prendre le
    cote le plus ancien pour reference est exactement l'erreur que ce module a faite
    une fois (cf. l'en-tete, `necroOverlord` / 1045).
    """
    ka, kb = set(a), set(b)
    if ka - kb:
        print("  cles seulement dans A : %s" % ", ".join(sorted(ka - kb)))
    if kb - ka:
        print("  cles seulement dans B : %s" % ", ".join(sorted(kb - ka)))

    divergentes = [s for s in SECTIONS_DE_FIDELITE if a.get(s) != b.get(s)]
    print("  sections de fidelite identiques : %d/%d"
          % (len(SECTIONS_DE_FIDELITE) - len(divergentes), len(SECTIONS_DE_FIDELITE)))
    for sec in divergentes:
        va, vb = a.get(sec), b.get(sec)
        print("  DIVERGE %s" % sec)
        if isinstance(va, dict) and isinstance(vb, dict):
            for k in sorted(set(va) | set(vb)):
                if va.get(k) != vb.get(k):
                    print("      %-34s A=%-24s B=%s"
                          % (k, json.dumps(va.get(k))[:24], json.dumps(vb.get(k))[:40]))
        else:
            print("      A=%s" % json.dumps(va)[:120])
            print("      B=%s" % json.dumps(vb)[:120])

    def taille(v):
        if isinstance(v, list):
            return "list[%d]" % len(v)
        if isinstance(v, dict):
            return "dict{%d}" % len(v)
        return str(v)[:20]

    print("  -- sections attendues DIFFERENTES (catalogue / board / poses) --")
    for sec in ("Units", "Abilities", "Utilities", "Board", "Tiles",
                "PredefinedUnits", "Player"):
        print("      %-16s A=%-12s B=%s" % (sec, taille(a.get(sec)), taille(b.get(sec))))
    return len(divergentes)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Regenere le seed BC par la fabrique native (sans bataille)")
    ap.add_argument("--out", default=None,
                    help=f"ou ecrire (defaut : {R.SEED_BC})")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"), default=None,
                    help="ne rien forger : comparer deux BC sur disque")
    ap.add_argument("--board", default=BOARD_TEMPLATE,
                    help=f"board du template forge (defaut {BOARD_TEMPLATE})")
    ap.add_argument("--no-amorce", action="store_true",
                    help="sauter l'amorce (deja faite cette session)")
    a = ap.parse_args()

    if a.diff:
        ba = json.loads(pathlib.Path(a.diff[0]).read_text(encoding="utf-8"))
        bb = json.loads(pathlib.Path(a.diff[1]).read_text(encoding="utf-8"))
        print("[forge] A=%s  B=%s" % (a.diff[0], a.diff[1]))
        return 0 if diff(ba, bb) == 0 else 1

    try:
        sid = R._resolve_session()
    except Exception as e:
        print(f"[error] pas de session Frida (lance Tacticus + inject): {e}",
              file=sys.stderr)
        return 2

    if not a.no_amorce:
        w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
        if not (isinstance(w, dict) and w.get("ok")):
            print(f"[error] amorce KO: {str(w)[:200]}", file=sys.stderr)
            return 2

    bc, bilan = forger(sid, a.board)
    cible = R.SEED_BC if a.out is None else pathlib.Path(a.out)
    texte = json.dumps(bc)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(texte, encoding="utf-8")

    print("[forge] %d octets -> %s" % (len(texte), cible))
    print("[forge]   Units=%s  lineup=%s  summons=%s  npc=%s  board=%s"
          % (bilan["units"], bilan["lineup"], bilan["summons"], bilan["npc"],
             bilan["board"]))
    print("[forge]   ramenes a la semantique campagne : %s"
          % (", ".join(bilan["ramenes_a_la_campagne"]) or "aucun"))
    # TOUJOURS annonce, y compris a zero : un catalogue ampute qui se tait se lit complet.
    ec = bilan["npc_ecartes"]
    if ec:
        print("[forge]   npc ECARTES (font lever le builder, derives par bisection) : %d"
              % len(ec))
        for x in ec:
            print("[forge]       %s" % x)
    else:
        print("[forge]   npc ecartes : aucun")
    return 0


if __name__ == "__main__":
    sys.exit(main())
