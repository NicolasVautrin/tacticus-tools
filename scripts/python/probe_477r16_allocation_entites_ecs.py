#!/usr/bin/env python
"""#477-r16 -- la REGLE d'allocation des entites ECS : derivee du decompile, confrontee live.

CE QUE CE PROBE TRANCHE
-----------------------
Un emetteur de flux cote port doit reproduire l'`Entity=<id>` de chaque ligne. Cet id est un
COMPTEUR D'ALLOCATION GLOBAL (#477-r15). La question est : sa sequence est-elle reproductible
depuis la `BattleConfiguration` ?

LA REGLE, LUE DANS LE DECOMPILE (aucune loi ajustee sur des mesures)
-------------------------------------------------------------------
Allocateur UNIQUE -- `IdunBattle.Entities.Components.MatchComponent$$NextId` :
    this.<+0x10> += 1 ; return this.<+0x10>          (PRE-incrementation)
`MatchComponent$$.ctor` pose le champ a **1**. `MatchComponent$$ReturnLastId` le decremente
(rollback), et n'est appele que par `AddTileOperation$$Execute` / `$$CreateTile`.

Les NEUF sites d'appel de `NextId` sont la liste EXHAUSTIVE des allocateurs (xrefs Ghidra) :
    AddPlayerOperation$$Execute .......................... 1 par joueur
    AddEnvironmentAbilityOperation$$Execute .............. 1 (deux sites EXCLUSIFS)
    AddEnvironmentAbilityOperation$$CreateEntity ......... 1 (deux sites EXCLUSIFS)
    AddTileOperation$$Execute / $$CreateTile ............. 1 par tuile, rollback si Build rend null
    AddUnitOperation$$Execute ........................... 1 + 1 PAR PIED (le 2e site est DANS
                                                           une boucle sur les tuiles occupees)
    AddMachineOperation$$Execute ........................ 1 par machine
    AddMachineOfWarPlatformOperation$$Execute ........... 1 par plateforme
    AddEffectOperation$$Execute ......................... 1 par effet

Ordre du deploiement -- `IdunBattle.Operations.SetupGameOperation$$Execute`, sequence FIXE :
    InitializeMatch(matchEntityId=1, ...)   -> l'entite Match prend l'id LITTERAL 1, puis
                                               `InitializeMatchOperation$$Execute` fait `+= 1`
                                               sur le compteur : il passe de 1 a 2, donc
                                               **l'id 2 n'est JAMAIS attribue**
    AddPlayers()                            -> SortedDictionary (ordre par cle, deterministe)
    AddEnvironmentAbilities()               -> List de `GetEnvironmentAbilities`
    AddTiles()                              -> for row in 0..Width-1 { for col in 0..Height-1 }
    SetupRoom()                             -> N'ALLOUE RIEN (absent des xrefs de NextId)
    AddMachinePlatform()                    -> DEUX appels (teams 2 puis 1), chacun alloue 1
    RevealHumanPlayerRoom()                 -> N'ALLOUE RIEN
    AddPredefinedUnits()                    -> puis AddPredefinedMachines, AddBossUnit

D'ou la prediction, SANS aucun parametre ajuste :
    premier id de tuile = 3 + P + E
    premier id d'unite  = premier id de tuile + T + 2      (T = Width * Height ; +2 = les
                                                            plateformes de Machine of War)
    ids de tuiles       = intervalle CONTIGU de longueur T
    pas entre deux unites mono-tuile = 2  (l'unite + son unique UnitFoot)

⚠ LE PIEGE PAYE ICI, et il faut le dire : la premiere version de ce probe predisait
`premier id d'unite = 3 + P + E + T` avec un E trop grand de 2 et SANS les plateformes.
Les deux fautes s'annulaient exactement : la prediction sur l'unite tombait juste sur les
TROIS boards (49 / 77 / 84) alors que l'offset des tuiles etait faux de 2. Un accord parfait
sur un seul point d'observation ne valide pas la decomposition -- c'est pour ca que le probe
verifie MAINTENANT chaque etage separement (offset des tuiles ET rang des unites).

P se lit dans le BC (`Player.Players`). E, lui, N'EST PAS ENTIEREMENT DANS LE BC. Le corps de
`SetupGameOperation$$GetEnvironmentAbilities` construit la liste dans CET ordre EXACT :

    list = new List<EnvironmentAbilityConfiguration>()
    list.AddRange(BC.EnvironmentAbilities.EnvironmentAbilities)              # AddRange -- pas de dedup
    list.AddRange(BC.EnvironmentAbilities.EnhancementsEnvironmentAbilities)  # idem
    foreach kv in BC.Abilities.PassiveAbilities:                             # Dictionary, cle seule lue
        d = StaticBattleRules.TriggeredAbility$$GetDerivedEnvironmentAbilities(kv.Key)
        if d != null: foreach x in d: list.Add(new EnvironmentAbilityConfiguration(x))  # Add DIRECT
    IncludeEnvironmentAbility(list, EnvDespoiledGroundTileDamage)            # DEDUPLIQUE
    IncludeEnvironmentAbility(list, EnvFireTileDamage)                       # DEDUPLIQUE
    foreach x in StaticBattleRules.DamageTrait$$GetDamageTraitAbilities(): list.Add(...)  # Add DIRECT
    if gameMode == SyncPVP: IncludeEnvironmentAbility(list, EnvCapturePointShield)        # DEDUPLIQUE

⚠ `IncludeEnvironmentAbility` N'EST PAS UN `Add` : elle appelle
`idun.shared.extensions.ListExtensions$$Contains<T>` avec un predicat sur l'id, et RETOURNE SANS
RIEN AJOUTER si la liste porte deja cette ability. Les trois termes qui passent par elle sont donc
CONDITIONNELS ; les deux boucles (derived, damage traits), elles, font un `List.Add` direct et ne
dedupliquent RIEN. La formule « |BC| + 2 + 3 + derived + syncpvp » de la premiere version de ce
probe est donc FAUSSE des que le BC porte deja l'une des trois. Elle reste juste sur le seed
courant parce que les deux listes du BC y sont VIDES.

⚠ La table des damage traits se lit dans `StaticBattleRules.DamageTrait$$.cctor` et contient TROIS
entrees. Elle NE SE DEDUIT PAS de l'enum `IdunBattle.Entities.Enum.DamageTrait`, qui porte SIX
membres : la premiere version de ce probe a fait exactement cette substitution et s'est trompee de
3. L'enum nomme des traits, la table nomme des ABILITIES -- deux choses differentes.

LE TERME `derived` EST LU, PLUS MESURE PAR DIFFERENCE (#477-r16-r1)
-------------------------------------------------------------------
`GetDerivedEnvironmentAbilities(passiveAbilityType : TriggeredAbilityType)` est un simple
`TryGetValue` sur un `Dictionary<TriggeredAbilityType, TriggeredAbilityType>` -- champ STATIQUE
`+0x38` de `StaticBattleRules.TriggeredAbility`, ecrit par son `.cctor`. La valeur trouvee est un
SCALAIRE, emballe par `IdunBattleLogic.Extensions.TExtensions$$ToList<T>` : le retour est donc une
liste a UN element, ou `null`. La table a DEUX entrees (lues au `.cctor`, cf.
`DERIVED_ENVIRONMENT_ABILITIES` ci-dessous), et la boucle appelante n'en lit que les CLES.

    derived = |{cles de la table} INTER {cles de BC.Abilities.PassiveAbilities}|   -- domaine 0..2

Le `1` observe sur le seed n'est donc PAS un scalaire ajuste : c'est `Ambush` present et
`PowerUp_ReinforcementShield` absent. Un terme obtenu par DIFFERENCE absorberait silencieusement
toute autre allocation manquee avant les tuiles -- ce probe le PREDIT maintenant, et
`--contre-derived` le fait VARIER expres (cf. plus bas).

CE QUE LE PROBE FAIT
--------------------
Volet OFFLINE (aucun runner) : re-derive P, E et la prediction depuis `data/` versionne.
Volet LIVE (--session)      : monte un runner par board, lit `replayOutputStream`, et
                              confronte la sequence reelle a la prediction IMPRIMEE AVANT.

⚠ Trois boards de TAILLES DISTINCTES sont imposes : deux boards de meme taille rendent les
memes ids et se lisent, a tort, comme une preuve d'independance (piege paye en #477-r15 :
MC1_67 et C1_70 font tous deux 63 tuiles). Deux points valident n'importe quelle droite --
le probe REFUSE de conclure sous trois tailles distinctes.

USAGE
    python scripts/python/probe_477r16_allocation_entites_ecs.py                 # offline seul
    python scripts/python/probe_477r16_allocation_entites_ecs.py --session <sid> # + confrontation
    python scripts/python/probe_477r16_allocation_entites_ecs.py --session <sid> --contre-derived
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import symbols_layout  # noqa: E402  -- foyer unique du "quel build fait foi"
from engine.entities.triggered_ability_type import TriggeredAbilityType as TAT  # noqa: E402

HERE = Path(__file__).resolve().parent
RACINE = HERE.parent.parent
DATA = RACINE / "data"
HOST = "http://127.0.0.1:8765"

# Les deux constantes ajoutees EN DUR par SetupGameOperation$$GetEnvironmentAbilities.
# Lues au decompile (`IncludeEnvironmentAbility(this, list, 0x5cb)` puis `(..., 0x18)`), pas
# devinees. Elles ne figurent nulle part dans la BattleConfiguration.
# ⚠ Elles passent par `IncludeEnvironmentAbility`, qui DEDUPLIQUE -- cf. en-tete.
ENV_ABILITIES_EN_DUR = (TAT.EnvDespoiledGroundTileDamage, TAT.EnvFireTileDamage)   # 0x5cb, 0x18
# Ajoutee seulement si le GameMode est SyncPVP (`idun.Shared.Battle.GameMode` 8=SyncPVP).
# Passe elle aussi par `IncludeEnvironmentAbility` -- donc dedupliquee.
ENV_ABILITY_SYNCPVP = TAT.EnvCapturePointShield                                   # 0x52e
# La table STATIQUE rendue par `StaticBattleRules.DamageTrait$$GetDamageTraitAbilities`,
# mirroree 1:1 depuis `StaticBattleRules.DamageTrait$$.cctor` : trois `List.Add` litteraux.
# ⚠ Ne PAS la re-deriver de l'enum `IdunBattle.Entities.Enum.DamageTrait` (6 membres) : ce sont
# des TRAITS, pas des abilities. Au changement de build, cette table peut bouger -- le residu
# mesure ci-dessous rougirait alors, et c'est le signal de la relire.
DAMAGE_TRAIT_ABILITIES = (TAT.OnFireDamageAbility, TAT.OnToxicDamageAbility,
                          TAT.OnOnMeltaDamageAbility)                    # 0x3f8, 0x4b3, 0x4bb
# La table STATIQUE lue par `StaticBattleRules.TriggeredAbility$$GetDerivedEnvironmentAbilities`
# (#477-r16-r1) -- mirror 1:1 du champ statique `+0x38` de `StaticBattleRules.TriggeredAbility`,
# ecrit par son `.cctor` : DEUX `Dictionary.Add` litteraux, cle puis valeur.
#   Add(key=0x4f5, value=0x4f6) ; Add(key=0x4f7, value=0x4fa)
# La fonction fait `TryGetValue(key, out v)` puis `TExtensions.ToList(v)` : le retour est une
# liste a UN element (ou `null`), JAMAIS davantage. La boucle appelante n'en lit que les CLES,
# et fait un `List.Add` DIRECT -- aucune deduplication sur ce terme.
DERIVED_ENVIRONMENT_ABILITIES = {
    TAT.PowerUp_ReinforcementShield: TAT.EnvReinforcementShield,          # 0x4f5 -> 0x4f6
    TAT.Ambush: TAT.EnvAmbushResurrect,                                   # 0x4f7 -> 0x4fa
}
# `SetupGameOperation$$AddMachinePlatform` : deux appels (teams 2 puis 1), chacun passe par
# `AddMachineOfWarPlatformOperation$$Execute`, qui alloue UNE entite. Emis dans le flux sous
# `Action=AddMachinePlatform`, ENTRE les tuiles et les unites.
NB_PLATEFORMES_MOW = 2

# Trois boards de tailles DISTINCTES : 5x7=35, 7x9=63, 7x10=70. Les trois tailles sont les
# SEULES presentes dans les ~780 dumps (verifie par balayage), donc ce triplet epuise l'axe.
BOARDS_DEFAUT = ("C1_02", "MC1_67", "C4_09")
ROSTER_P = "adeptCanoness,adeptCanoness,adeptRetributor"
ROSTER_A = "adeptHospitaller,adeptMorvenn"


class MesureImpossible(RuntimeError):
    """Une source manque -- on le DIT, on ne rend pas un verdict."""


# --------------------------------------------------------------------------- offline

def build_courant() -> str:
    """Le build qui FAIT FOI -- foyer unique `symbols_layout`, jamais un choix local.

    ⚠ La premiere version de ce probe re-derivait ce choix a la main et retenait
    `gqfc5mff6c` (ARCHIVE) au lieu de `rnca9r7q6c` : exactement la desynchronisation
    silencieuse que `data/symbols/CURRENT` existe pour empecher.
    """
    try:
        return symbols_layout.current_build()
    except symbols_layout.LayoutError as e:
        raise MesureImpossible(str(e)) from e


def membres_enum(build: str, nom: str) -> dict[int, str]:
    """{ordinal: nom} pour un enum de la table versionnee. Leve si l'enum a disparu."""
    f = symbols_layout.build_dir(build) / "frida" / "enums.tsv"
    if not f.is_file():
        raise MesureImpossible("table d'enums absente : %s" % f)
    for ligne in f.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#!"):
            continue
        champs = ligne.split("\t")
        if len(champs) >= 2 and champs[0] == nom:
            out = {}
            for m in champs[1].split(","):
                if "=" in m:
                    k, v = m.split("=", 1)
                    out[int(k)] = v
            return out
    raise MesureImpossible("enum introuvable dans la table du build %s : %s" % (build, nom))


def lire_seed_bc(path=None) -> dict:
    """Le BC tel que `rl_duel build` l'ENVERRA -- pas le fichier brut.

    ⚠ La difference n'est pas cosmetique : `_load_seed_bc` re-synthetise `BC.Abilities` depuis le
    gameconfig vivant (#254) et peut donc AJOUTER des cles a `PassiveAbilities`. Predire `derived`
    sur le fichier brut, c'est predire sur une entree que le natif ne verra pas.
    """
    f = Path(path) if path else (DATA / "seed-bc.json")
    if not f.is_file():
        raise MesureImpossible("seed BC absent : %s (python dump_boards.py)" % f)
    try:
        from rl_collect_batch import _load_seed_bc          # import tardif : charge le gameconfig
        return _load_seed_bc(str(f))
    except MesureImpossible:
        raise
    except Exception as e:                                   # gameconfig absent, catalogue casse...
        raise MesureImpossible("seed BC illisible via _load_seed_bc (%s) : %s" % (f, e)) from e


def ids_env_abilities_du_bc(bc: dict) -> tuple[list, list]:
    """Les ids deja presents dans les DEUX listes `AddRange`-ees, et ce qu'on n'a pas su lire.

    Ils decident si les trois termes qui passent par `IncludeEnvironmentAbility` (deduplique)
    comptent ou non. Rend `(ids_lus, elements_non_lus)` -- on ne fabrique JAMAIS un zero : un
    element dont on ne sait pas extraire l'id est REMONTE, pas ignore.
    """
    env = bc.get("EnvironmentAbilities") or {}
    lus, opaques = [], []
    for cle in ("EnvironmentAbilities", "EnhancementsEnvironmentAbilities"):
        for item in (env.get(cle) or []):
            brut = item.get("Id") if isinstance(item, dict) else None
            if isinstance(brut, dict):                      # TriggeredAbilityConfigId serialise
                brut = brut.get("Type", brut.get("AbilityType"))
            if isinstance(brut, str) and brut in TAT.__members__:
                lus.append(TAT[brut])
            elif isinstance(brut, int):
                lus.append(brut)
            else:
                opaques.append(item)
    return lus, opaques


def taille_board(board_id: str) -> tuple[int, int]:
    """(Width, Height) du dump versionne. T = Width * Height = nb de cellules balayees."""
    for kind in ("pvp", "syncPvp", "global"):
        f = DATA / "boards" / kind / ("%s.json" % board_id)
        if f.is_file():
            b = json.loads(f.read_text(encoding="utf-8"))["board"]
            return int(b["Width"]), int(b["Height"])
    raise MesureImpossible("board absent des dumps versionnes : %s (python dump_boards.py)" % board_id)


def deriver_regle(seed_bc_path=None) -> dict:
    """Re-derive P, E (derived COMPRIS) et l'offset depuis les ENTREES. Aucun chiffre ajuste."""
    build = build_courant()
    bc = lire_seed_bc(seed_bc_path)

    joueurs = (bc.get("Player") or {}).get("Players") or {}
    p = len(joueurs)

    deja, opaques = ids_env_abilities_du_bc(bc)
    e_bc = len(deja) + len(opaques)
    if opaques:
        raise MesureImpossible(
            "%d element(s) de BC.EnvironmentAbilities dont l'id est illisible : la deduplication "
            "d'IncludeEnvironmentAbility n'est pas decidable -- lire la forme et etendre "
            "`ids_env_abilities_du_bc` (exemple : %r)" % (len(opaques), opaques[0]))

    # `derived` -- LU, plus mesure par difference (#477-r16-r1). La boucle native ne lit que les
    # CLES de BC.Abilities.PassiveAbilities, et n'ajoute qu'un element par cle TROUVEE dans la
    # table statique. Conversion PAR NOM (jamais par ordinal ni par la voie -- cf. #270-c).
    passifs = set((bc.get("Abilities") or {}).get("PassiveAbilities") or {})
    touches = sorted(k.name for k in DERIVED_ENVIRONMENT_ABILITIES if k.name in passifs)
    derived = len(touches)

    n_traits = len(DAMAGE_TRAIT_ABILITIES)

    modes = membres_enum(build, "idun.Shared.Battle.GameMode")
    mode_nom = bc.get("GameMode")
    est_syncpvp = (mode_nom == modes.get(8))

    # Les trois termes qui passent par `IncludeEnvironmentAbility` sont CONDITIONNELS : elle
    # retourne sans rien ajouter si l'id est deja dans la liste. Etat de la liste a ce moment :
    # les deux AddRange du BC, PLUS ce que la boucle `derived` vient d'ajouter (Add direct).
    presents = set(deja) | {DERIVED_ENVIRONMENT_ABILITIES[k] for k in DERIVED_ENVIRONMENT_ABILITIES
                            if k.name in passifs}
    e_en_dur = 0
    for a in ENV_ABILITIES_EN_DUR:
        if a not in presents:
            e_en_dur += 1
            presents.add(a)
    e_syncpvp = 1 if (est_syncpvp and ENV_ABILITY_SYNCPVP not in presents) else 0

    e_lu = e_bc + derived + e_en_dur + n_traits + e_syncpvp
    return {
        "build": build,
        "P": p,
        "cles_joueurs": sorted(joueurs, key=lambda k: int(k)) if joueurs else [],
        "seed_bc": str(seed_bc_path) if seed_bc_path else "data/seed-bc.json",
        "E_bc": e_bc,
        "E_derived": derived,
        "E_derived_cles": touches,
        "E_en_dur": e_en_dur,
        "E_damage_traits": n_traits,
        "E_syncpvp": e_syncpvp,
        "E_lu": e_lu,
        "game_mode": mode_nom,
        # premier id de tuile = 3 + P + E  (cf. en-tete : match=1, compteur a 2 apres
        # InitializeMatch, donc le premier NextId rend 3). E est ENTIEREMENT lu : plus aucun
        # terme n'est laisse a la mesure, donc plus rien ne peut absorber une erreur voisine.
        "premier_id_tuile_prevu": 3 + p + e_lu,
        # Ce que vaudrait l'offset si `derived` etait laisse en inconnue -- sert au diagnostic :
        # `derived_mesure` = premier_id_tuile - cette base.
        "premier_id_tuile_sans_derived": 3 + p + e_lu - derived,
    }


# ----------------------------------------------------------------------------- live

def rpc(session: int, method: str, args: dict, timeout: int = 60) -> dict:
    body = json.dumps({"method": method, "args": [args], "timeout": 45000}).encode()
    req = urllib.request.Request("%s/api/scripts/%d/rpc" % (HOST, session), data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("result") or {}
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("RPC %s injoignable : %s" % (method, e)) from e


def build_runner(board: str, state_file: Path, mow: str | None = None,
                 seed_bc: Path | None = None) -> int:
    if state_file.exists():
        state_file.unlink()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "777", "--board", board,
           "--p-units", ROSTER_P, "--a-units", ROSTER_A,
           "--record-replay", "--no-ai", "--state-file", str(state_file)]
    if mow:
        cmd += ["--p-mow", mow]
    if seed_bc:
        cmd += ["--seed-bc", str(seed_bc)]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=900)
    if not state_file.is_file():
        sortie = (p.stderr or "") + (p.stdout or "")
        if "maintenance" in sortie or "runner creation paused" in sortie or "503" in sortie:
            raise MesureImpossible("NON CONFRONTE -- fenetre DRAIN (creation de runner refusee)")
        raise MesureImpossible("build %s echoue : %s" % (board, sortie[-400:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


# Les actions du flux qui correspondent a une ALLOCATION (une entite creee). Les autres
# actions (`ChangeStats`, `ReceiveEffect`, ...) PORTENT un `Entity=` deja alloue : les
# compter ferait croire a des doublons.
ACTIONS_ALLOUANTES = ("AddPlayer", "AddTile", "AddMachinePlatform", "AddUnit")


def sequence_du_flux(flux: str) -> dict:
    """Extrait, dans l'ordre du flux, les `Entity=` de chaque famille d'action."""
    out = {a: [] for a in ACTIONS_ALLOUANTES}
    out["ordre"] = []
    for s in flux.split("\n"):
        m = re.match(r"\s*Action=(\w+) Entity=(-?\d+)", s)
        if not m:
            continue
        act, ent = m.group(1), int(m.group(2))
        out["ordre"].append((act, ent))
        if act in out:
            out[act].append(ent)
    return out


def mesurer_board(session: int, board: str) -> dict:
    w, h = taille_board(board)
    tmp = Path(tempfile.gettempdir()) / ("r16-alloc-%s.json" % board)
    rid = build_runner(board, tmp)
    try:
        flux = rpc(session, "replayOutputStream", {"runnerId": rid}).get("outputStream") or ""
        if not flux:
            raise MesureImpossible("flux VIDE sur %s -- enregistreur non arme ?" % board)
        seq = sequence_du_flux(flux)
        return {
            "board": board, "runner": rid, "W": w, "H": h, "T_attendu": w * h,
            "tuiles": seq["AddTile"], "unites": seq["AddUnit"],
            "joueurs": seq["AddPlayer"], "plateformes": seq["AddMachinePlatform"],
            "actions_distinctes": sorted({a for a, _ in seq["ordre"]}),
        }
    finally:
        try:
            rpc(session, "disposeRunner", {"runnerId": rid}, timeout=45)
        except MesureImpossible:
            pass


def analyser(m: dict, r: dict) -> dict:
    """Confronte UNE mesure a la prediction, ETAGE PAR ETAGE.

    Rien n'est ajuste sauf le terme `derived` (table statique non lue), qui est MESURE et
    dont l'invariance par board est verifiee separement. Chaque etage a son propre verdict :
    un accord global qui masquerait deux erreurs opposees ne peut plus passer.
    """
    tuiles, unites = m["tuiles"], m["unites"]
    joueurs, plateformes = m["joueurs"], m["plateformes"]
    a = {"board": m["board"]}

    a["nb_joueurs"] = len(joueurs)
    a["joueurs_concordent"] = (joueurs == list(range(3, 3 + r["P"])))

    a["nb_tuiles"] = len(tuiles)
    a["T_concorde"] = (len(tuiles) == m["T_attendu"])
    a["tuiles_contigues"] = bool(tuiles) and tuiles == list(range(tuiles[0], tuiles[0] + len(tuiles)))
    a["premier_id_tuile"] = tuiles[0] if tuiles else None
    # Ce que `GetDerivedEnvironmentAbilities` a ajoute a la liste, DEDUIT de l'offset mesure.
    # Il n'est plus le terme libre du modele (il est PREDIT par `E_derived`, cf. `deriver_regle`) :
    # c'est desormais une CONFRONTATION, et l'ecart accuse le modele au lieu d'etre absorbe.
    a["derived_mesure"] = (a["premier_id_tuile"] - r["premier_id_tuile_sans_derived"]
                           if tuiles else None)
    a["derived_prevu"] = r["E_derived"]
    a["derived_concorde"] = (a["derived_mesure"] == r["E_derived"])
    a["premier_id_tuile_prevu"] = r["premier_id_tuile_prevu"]
    a["tuile_concorde"] = (a["premier_id_tuile"] == r["premier_id_tuile_prevu"])

    a["nb_plateformes"] = len(plateformes)
    a["plateformes_concordent"] = (len(plateformes) == NB_PLATEFORMES_MOW)
    a["plateformes_apres_tuiles"] = bool(
        tuiles and plateformes and plateformes[0] == tuiles[-1] + 1
        and plateformes == list(range(plateformes[0], plateformes[0] + len(plateformes))))

    a["premier_id_unite"] = unites[0] if unites else None
    a["premier_id_unite_prevu"] = (
        a["premier_id_tuile"] + m["T_attendu"] + NB_PLATEFORMES_MOW if tuiles else None)
    a["unite_concorde"] = (a["premier_id_unite"] == a["premier_id_unite_prevu"])
    a["pas_unites"] = [b - x for x, b in zip(unites, unites[1:])]
    a["pas_tous_a_2"] = all(d == 2 for d in a["pas_unites"]) if a["pas_unites"] else None

    # COUVERTURE. Deux familles d'entites allouees n'ont AUCUNE ligne propre dans le flux :
    #   * les `UnitFoot` -- une par tuile occupee, allouee dans la boucle de
    #     `AddUnitOperation$$Execute` ; sur des unites mono-tuile, c'est l'id juste apres ;
    #   * les ENVIRONMENT ABILITIES -- `AddEnvironmentAbilityOperation$$Execute` alloue mais
    #     n'emet pas d'action ; leur bloc est exactement [dernier joueur+1 .. 1re tuile-1].
    # Les reconstituer est ce qui rend le test de couverture HONNETE : sans elles il rougit
    # sur des entites parfaitement expliquees (mesure : trous = [6..11] = les 6 env abilities).
    pieds = [u + 1 for u in unites]
    env_implicites = (list(range(3 + r["P"], a["premier_id_tuile"])) if tuiles else [])
    a["env_implicites"] = len(env_implicites)
    couvert = sorted(set(joueurs + env_implicites + tuiles + plateformes + unites + pieds))
    a["union_contigue_depuis_3"] = bool(couvert) and couvert == list(range(3, 3 + len(couvert)))
    a["trous"] = ([x for x in range(3, max(couvert) + 1) if x not in set(couvert)][:12]
                  if couvert else [])
    return a


# ------------------------------------------------------- contre-epreuve MULTI-TUILES

def blocs_addunit(flux: str) -> list[dict]:
    """[{entity, feet}] par `Action=AddUnit` ; `feet` = nb de `Tag=Unit_Foot_Tile_Id_<n>`.

    C'est LE discriminant de la lecture : `AddUnitOperation$$Execute` alloue 1 entite pour
    l'unite PUIS une par tuile occupee, dans une BOUCLE. Un « pas de 2 » observe sur des
    unites mono-tuile ne distingue pas cette lecture d'un simple « deux entites par unite ».
    """
    lignes = flux.split("\n")
    out, i = [], 0
    while i < len(lignes):
        s = lignes[i]
        m = re.match(r"(\s*)Action=AddUnit Entity=(-?\d+)", s)
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        feet, j = 0, i + 1
        while j < len(lignes):
            t = lignes[j]
            if t.strip() and (len(t) - len(t.lstrip())) <= indent:
                break
            if re.match(r"\s*Tag=Unit_Foot_Tile_Id_\d+:", t):
                feet += 1
            j += 1
        out.append({"entity": int(m.group(2)), "feet": feet})
        i = j
    return out


def contre_epreuve_mow(session: int, board: str, mow: str) -> dict:
    """Monte un runner AVEC Machine of War et confronte le pas de chaque unite.

    La MoW ne sert pas a produire une unite multi-pieds -- `AddMachineOperation$$Execute`
    alloue UNE entite et AUCUN pied (`Blueprints$$Machine`, pas `Blueprints$$Unit`). Elle
    sert a verifier que le pas entre deux `AddUnit` s'explique ENTIEREMENT par
    `1 + feet + (entites d'AUTRES familles allouees entre les deux)` : sans ce terme, la
    machine intercalee fait apparaitre un pas de 3 qui se lirait, a tort, comme un ecart.
    """
    tmp = Path(tempfile.gettempdir()) / ("r16-mow-%s.json" % board)
    rid = build_runner(board, tmp, mow=mow)
    try:
        flux = rpc(session, "replayOutputStream", {"runnerId": rid}).get("outputStream") or ""
        if not flux:
            raise MesureImpossible("flux VIDE (enregistreur non arme ?)")
        blocs = blocs_addunit(flux)
        seq = sequence_du_flux(flux)
        # premiere action de chaque entite -> qui a alloue quoi
        premiere = {}
        for act, ent in seq["ordre"]:
            premiere.setdefault(ent, act)
        autres = {e for e, act in premiere.items() if act in ("AddMachine", "AddMachinePlatform")}
        lignes = []
        for k, b in enumerate(blocs[:-1]):
            suivant = blocs[k + 1]["entity"]
            intercales = len([e for e in autres if b["entity"] < e < suivant])
            attendu = 1 + b["feet"] + intercales
            lignes.append({"entity": b["entity"], "feet": b["feet"],
                           "pas": suivant - b["entity"], "intercales": intercales,
                           "attendu": attendu, "concorde": (suivant - b["entity"]) == attendu})
        return {"board": board, "runner": rid, "mow": mow, "blocs": blocs, "lignes": lignes,
                "machines": sorted(autres)}
    finally:
        try:
            rpc(session, "disposeRunner", {"runnerId": rid}, timeout=45)
        except MesureImpossible:
            pass


# ------------------------------------------------- contre-epreuve `derived` (#477-r16-r1)

SORTIES = RACINE / "logs" / "probe_477r16r1"


def _ecrire_variante(nom: str, muter) -> Path:
    """Ecrit un seed BC derive du seed versionne, mute par `muter(bc)`. Sortie dans `logs/`."""
    src = DATA / "seed-bc.json"
    if not src.is_file():
        raise MesureImpossible("seed BC absent : %s (python dump_boards.py)" % src)
    bc = json.loads(src.read_text(encoding="utf-8"))
    muter(bc)
    SORTIES.mkdir(parents=True, exist_ok=True)
    p = SORTIES / ("seed-bc-%s.json" % nom)
    p.write_text(json.dumps(bc), encoding="utf-8")
    return p


def variantes_derived() -> list[dict]:
    """Les seeds BC qui font VARIER `derived`, un par cle de la table statique.

    Pour chaque cle de `DERIVED_ENVIRONMENT_ABILITIES` : si elle est dans le seed on la RETIRE
    (derived -1), sinon on l'AJOUTE (derived +1). C'est le contre-test nomme par #477-r16 --
    « changer de seed BC doit DECALER l'offset ; s'il ne bouge pas, la lecture est fausse » --
    mais rendu PREDICTIF : on sait de combien, et dans quel sens, AVANT de mesurer.
    """
    base = lire_seed_bc()
    passifs = set((base.get("Abilities") or {}).get("PassiveAbilities") or {})
    out = []
    for cle in DERIVED_ENVIRONMENT_ABILITIES:
        nom = cle.name
        if nom in passifs:
            def muter(bc, _n=nom):
                bc.setdefault("Abilities", {}).setdefault("PassiveAbilities", {}).pop(_n, None)
            sens, delta = "RETIRE", -1
        else:
            try:
                import catalog_inject
                cfg = catalog_inject.synthesize_ability(nom)
            except Exception as e:
                out.append({"cle": nom, "sens": "AJOUTE", "delta": +1, "path": None,
                            "pourquoi": "config non synthetisable depuis le gameconfig : %s" % e})
                continue

            def muter(bc, _n=nom, _c=cfg):
                bc.setdefault("Abilities", {}).setdefault("PassiveAbilities", {})[_n] = _c
            sens, delta = "AJOUTE", +1
        out.append({"cle": nom, "sens": sens, "delta": delta,
                    "path": _ecrire_variante(nom.lower() + "-" + sens.lower(), muter),
                    "pourquoi": None})
    return out


def contre_epreuve_derived(session: int, board: str, temoin: dict) -> list[dict]:
    """Monte un runner par variante et confronte l'offset des tuiles a la prediction.

    ⚠ DEUX crans, pas un. (1) La MUTATION doit avoir mordu : `_load_seed_bc` re-synthetise
    `BC.Abilities` (#254) et pourrait recombler une cle retiree -- si `derived_prevu` de la
    variante egale celui du temoin, le regime est DEGENERE et le probe REFUSE de conclure au lieu
    de rendre un vert. (2) L'offset doit BOUGER de `delta` exactement : s'il ne bouge pas, la
    lecture de `GetDerivedEnvironmentAbilities` est REFUTEE -- et c'est un resultat, pas un echec.
    """
    w, h = taille_board(board)
    lignes = []
    for v in variantes_derived():
        if v["path"] is None:
            lignes.append(dict(v, statut="PAS MESURE"))
            continue
        r = deriver_regle(v["path"])
        attendu = temoin["premier_id_tuile_prevu"] + v["delta"]
        mordu = (r["E_derived"] == temoin["E_derived"] + v["delta"]
                 and r["premier_id_tuile_prevu"] == attendu)
        if not mordu:
            lignes.append(dict(v, statut="DEGENERE", derived_prevu=r["E_derived"],
                               pourquoi="la mutation n'a pas mordu (derived prevu %d, temoin %d)"
                                        % (r["E_derived"], temoin["E_derived"])))
            continue
        tmp = Path(tempfile.gettempdir()) / ("r16r1-%s.json" % v["cle"].lower())
        try:
            rid = build_runner(board, tmp, seed_bc=v["path"])
        except MesureImpossible as e:
            lignes.append(dict(v, statut="PAS MESURE", pourquoi=str(e)))
            continue
        try:
            flux = rpc(session, "replayOutputStream", {"runnerId": rid}).get("outputStream") or ""
            seq = sequence_du_flux(flux)
            tuiles = seq["AddTile"]
            mesure = tuiles[0] if tuiles else None
            lignes.append(dict(v, statut="MESURE", runner=rid, derived_prevu=r["E_derived"],
                               premier_id_tuile=mesure, attendu=attendu,
                               nb_tuiles=len(tuiles), T_attendu=w * h,
                               concorde=(mesure == attendu)))
        finally:
            try:
                rpc(session, "disposeRunner", {"runnerId": rid}, timeout=45)
            except MesureImpossible:
                pass
    return lignes


# ---------------------------------------------------------------------------- sortie

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", type=int, default=None,
                    help="id de session Frida ; sans lui, seul le volet OFFLINE tourne")
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT),
                    help="boards a jouer -- TAILLES DISTINCTES exigees (au moins trois)")
    ap.add_argument("--mow", default=None, metavar="UNIT_ID",
                    help="contre-epreuve MULTI-TUILES : monte un 4e runner avec cette Machine "
                         "of War et verifie que son pas vaut 1 + nb de pieds (et non 2)")
    ap.add_argument("--contre-derived", action="store_true",
                    help="contre-epreuve #477-r16-r1 : monte un runner par cle de "
                         "`DERIVED_ENVIRONMENT_ABILITIES`, sur un seed BC ou cette cle est "
                         "retiree/ajoutee de BC.Abilities.PassiveAbilities, et verifie que "
                         "l'offset des tuiles se decale de -1/+1. S'il ne bouge PAS, la lecture "
                         "de GetDerivedEnvironmentAbilities est REFUTEE.")
    a = ap.parse_args()

    print("=" * 78)
    print("#477-r16 -- regle d'allocation des entites ECS")
    print("=" * 78)

    try:
        r = deriver_regle()
    except MesureImpossible as e:
        print("VERDICT : PAS MESURE -- %s" % e)
        return 2

    print("\n[OFFLINE] la regle, re-derivee des entrees versionnees (build %s)" % r["build"])
    print("  MatchComponent$$.ctor pose le compteur a 1 ; InitializeMatchOperation$$Execute")
    print("  l'incremente -> 2. Entite Match = id 1 (litteral), et l'id 2 n'est JAMAIS attribue.")
    print("  P (Player.Players du seed BC) ........................ %d  %s"
          % (r["P"], r["cles_joueurs"]))
    print("  E = env abilities allouees, decomposee (seed BC : %s) :" % r["seed_bc"])
    print("      AddRange des 2 listes de BC.EnvironmentAbilities . %d" % r["E_bc"])
    print("      derived = TriggeredAbility$$GetDerivedEnvironmentAbilities ... %d  %s"
          % (r["E_derived"], r["E_derived_cles"] or "(aucune cle du BC dans la table)"))
    print("        table statique `+0x38`, %d entrees : %s"
          % (len(DERIVED_ENVIRONMENT_ABILITIES),
             ["%s->%s" % (k.name, v.name) for k, v in DERIVED_ENVIRONMENT_ABILITIES.items()]))
    print("      IncludeEnvironmentAbility EN DUR (DEDUPLIQUE) ... %d / %d  %s"
          % (r["E_en_dur"], len(ENV_ABILITIES_EN_DUR), [x.name for x in ENV_ABILITIES_EN_DUR]))
    print("      table DamageTrait$$.cctor (LUE, pas l'enum) ...... %d  %s"
          % (r["E_damage_traits"], [x.name for x in DAMAGE_TRAIT_ABILITIES]))
    print("      SyncPVP (%s, DEDUPLIQUE) -- GameMode=%s ... %d"
          % (ENV_ABILITY_SYNCPVP.name, r["game_mode"], r["E_syncpvp"]))
    print("      -> E LU ......................................... %d" % r["E_lu"])
    print("  PREDICTION  premier id de tuile = 3 + P + E = %d" % r["premier_id_tuile_prevu"])
    print("              premier id d'unite   = premier id de tuile + Width*Height + %d"
          % NB_PLATEFORMES_MOW)
    print("  PLUS AUCUN TERME LIBRE (#477-r16-r1) : `derived` etait mesure par DIFFERENCE, donc")
    print("    il absorbait silencieusement toute autre allocation manquee avant les tuiles. Il")
    print("    est desormais LU (table statique mirroree ci-dessus) et CONFRONTE ; `--contre-")
    print("    derived` le fait VARIER expres pour verifier qu'il n'est pas un scalaire ajuste.")

    if a.session is None:
        print("\n[LIVE] PAS MESURE -- aucune --session fournie (volet offline seul).")
        print("VERDICT : regle DERIVEE, NON CONFRONTEE.")
        return 0

    boards = [x.strip() for x in a.boards.split(",") if x.strip()]
    tailles = {}
    for b in boards:
        try:
            w, h = taille_board(b)
            tailles[b] = w * h
        except MesureImpossible as e:
            print("\n[LIVE] board ecarte : %s" % e)
    if len(set(tailles.values())) < 3:
        print("\n[LIVE] REFUS DE CONCLURE : %d taille(s) distincte(s) parmi %s."
              % (len(set(tailles.values())), tailles))
        print("  Deux points valident n'importe quelle droite -- il en faut TROIS, de tailles")
        print("  differentes. Piege deja paye : MC1_67 et C1_70 font tous deux 63 tuiles.")
        return 2

    print("\n[LIVE] prediction par board, IMPRIMEE AVANT LA MESURE (aucun terme libre) :")
    base = r["premier_id_tuile_prevu"]
    for b in boards:
        if b in tailles:
            print("  %-9s T=%-3d -> tuiles %d..%d, plateformes MoW, unite %d"
                  % (b, tailles[b], base, base + tailles[b] - 1,
                     base + tailles[b] + NB_PLATEFORMES_MOW))

    mesures, drain = [], False
    for b in boards:
        if b not in tailles:
            continue
        try:
            mesures.append(mesurer_board(a.session, b))
        except MesureImpossible as e:
            print("  PAS MESURE (%s) : %s" % (b, e))
            if "DRAIN" in str(e):
                drain = True
    if not mesures:
        print("\nVERDICT : %s" % ("NON CONFRONTE -- fenetre DRAIN." if drain
                                  else "PAS MESURE -- aucun board monte."))
        return 2

    analyses = [analyser(m, r) for m in mesures]
    print("\n[LIVE] mesure")
    for m, an in zip(mesures, analyses):
        print("\n  [%s] runner=%d, %dx%d = %d cellules ; actions du flux : %s"
              % (m["board"], m["runner"], m["W"], m["H"], m["T_attendu"], m["actions_distinctes"]))
        print("      joueurs .... %s (attendu %s) -> %s"
              % (m["joueurs"], list(range(3, 3 + r["P"])),
                 "OK" if an["joueurs_concordent"] else "ECART"))
        print("      tuiles ..... %d emises (attendu %d), contigues=%s, 1re=%s (prevu %s) -> %s"
              % (an["nb_tuiles"], m["T_attendu"], an["tuiles_contigues"], an["premier_id_tuile"],
                 an["premier_id_tuile_prevu"], "OK" if an["tuile_concorde"] else "ECART"))
        print("                   => derived  mesure=%s  prevu=%s  -> %s"
              % (an["derived_mesure"], an["derived_prevu"],
                 "OK" if an["derived_concorde"] else "ECART"))
        print("      MoW ........ %s (attendu %d, juste apres les tuiles=%s)"
              % (m["plateformes"], NB_PLATEFORMES_MOW, an["plateformes_apres_tuiles"]))
        print("      unites ..... %s" % m["unites"])
        print("                   1re=%s (prevu %s) -> %s ; pas=%s"
              % (an["premier_id_unite"], an["premier_id_unite_prevu"],
                 "OK" if an["unite_concorde"] else "ECART", an["pas_unites"]))
        print("      couverture 3..max sans trou (env %d + pieds %d reconstitues) : %s%s"
              % (an["env_implicites"], len(m["unites"]), an["union_contigue_depuis_3"],
                 "" if an["union_contigue_depuis_3"] else "  trous=%s" % an["trous"]))

    tout_T = all(x["T_concorde"] for x in analyses)
    tout_contigu = all(x["tuiles_contigues"] for x in analyses)
    tout_joueurs = all(x["joueurs_concordent"] for x in analyses)
    tout_mow = all(x["plateformes_concordent"] and x["plateformes_apres_tuiles"] for x in analyses)
    tout_unite = all(x["unite_concorde"] for x in analyses)
    tout_pas2 = all(x["pas_tous_a_2"] for x in analyses)
    tout_couvert = all(x["union_contigue_depuis_3"] for x in analyses)
    deriveds = {x["derived_mesure"] for x in analyses}

    print("\n" + "-" * 78)
    print("VERDICT")
    print("  1. ids des joueurs == 3..2+P (SortedDictionary) ............... %s" % ("OUI" if tout_joueurs else "NON"))
    print("  2. nb de tuiles emises == Width*Height ........................ %s" % ("OUI" if tout_T else "NON"))
    print("  3. ids de tuiles CONTIGUS ..................................... %s" % ("OUI" if tout_contigu else "NON"))
    print("  4. 2 plateformes MoW, juste apres les tuiles .................. %s" % ("OUI" if tout_mow else "NON"))
    print("  5. premier id d'unite == 1re tuile + T + 2 .................... %s" % ("OUI" if tout_unite else "NON"))
    print("  6. pas entre unites mono-tuile == 2 (unite + UnitFoot) ........ %s" % ("OUI" if tout_pas2 else "NON"))
    print("  7. aucun TROU dans 3..max (env + pieds reconstitues) .......... %s" % ("OUI" if tout_couvert else "NON"))
    print("  8. terme `derived` INVARIANT par board (%s) ................. %s"
          % (sorted(deriveds), "OUI" if len(deriveds) == 1 else "NON"))
    tout_derived = all(x["derived_concorde"] for x in analyses)
    print("  8bis. `derived` MESURE == `derived` LU dans la table statique (%d) ... %s"
          % (r["E_derived"], "OUI" if tout_derived else "NON"))
    if not tout_derived:
        print("     -> ECART : la table `+0x38` de StaticBattleRules.TriggeredAbility a bouge,")
        print("        OU une allocation non recensee precede les tuiles. C'est exactement ce")
        print("        qu'un terme mesure par DIFFERENCE aurait absorbe en silence.")
    ok = (tout_joueurs and tout_T and tout_contigu and tout_mow and tout_unite
          and tout_pas2 and tout_couvert and len(deriveds) == 1 and tout_derived)

    if a.mow:
        print("\n  9. pas d'unite avec une MACHINE OF WAR intercalee (--mow %s)" % a.mow)
        try:
            ce = contre_epreuve_mow(a.session, boards[0], a.mow)
            print("       entites non-unite allouees : %s" % ce["machines"])
            for x in ce["lignes"]:
                print("       entite %-4d feet=%-2d intercalees=%-2d pas=%-2d (attendu %-2d) %s"
                      % (x["entity"], x["feet"], x["intercales"], x["pas"], x["attendu"],
                         "OK" if x["concorde"] else "ECART"))
            if all(x["concorde"] for x in ce["lignes"]):
                print("       => tout pas s'explique par 1 + feet + intercalees.")
            else:
                print("       => ECART inexplique : la regle est MISE EN DEFAUT.")
                ok = False
            multi = [x for x in ce["lignes"] if x["feet"] > 1]
            if not multi:
                print("       (!) NON CONFRONTE : aucune unite a PLUSIEURS pieds ici, et c'est")
                print("         STRUCTUREL -- `AddPredefinedUnits` passe `ToList(<un tileId>)`,")
                print("         donc une liste a UN element ; et une Machine of War n'a AUCUN")
                print("         pied (`Blueprints$$Machine`). Le porteur multi-pieds est le")
                print("         BOSS (`AddBossUnit` / `GetBossPlatform`). La BOUCLE sur les")
                print("         pieds reste donc LUE au decompile, non confrontee. #477-r16-r2.")
        except MesureImpossible as e:
            print("       PAS MESURE : %s" % e)
            ok = False
    else:
        print("\n  9. pas d'unite avec MoW intercalee ............................ NON JOUEE")
        print("     Rejouer avec --mow <MoW du pool> pour verifier qu'un pas > 2 s'explique.")

    if a.contre_derived:
        print("\n  10. `derived` FAIT VARIER expres (#477-r16-r1) -- board %s" % boards[0])
        print("      Un terme qui tombe juste sur trois boards ne prouve rien s'il ne peut pas")
        print("      varier : les trois boards partagent le MEME seed BC, donc le meme `derived`.")
        print("      On le change a la source et on verifie que l'offset SUIT.")
        lignes = contre_epreuve_derived(a.session, boards[0], r)
        joue = 0
        for x in lignes:
            if x["statut"] != "MESURE":
                print("      %-28s %-7s %s : %s"
                      % (x["cle"], x["sens"], x["statut"], x.get("pourquoi") or ""))
                if x["statut"] == "DEGENERE":
                    ok = False
                continue
            joue += 1
            print("      %-28s %-7s derived %d -> %d ; 1re tuile mesuree=%s (attendu %s) %s"
                  % (x["cle"], x["sens"], r["E_derived"], x["derived_prevu"],
                     x["premier_id_tuile"], x["attendu"], "OK" if x["concorde"] else "ECART"))
            if x["nb_tuiles"] != x["T_attendu"]:
                print("        (!) %d tuiles emises pour %d attendues -- le montage a change autre"
                      " chose que `derived`." % (x["nb_tuiles"], x["T_attendu"]))
            if not x["concorde"]:
                ok = False
                if x["premier_id_tuile"] == r["premier_id_tuile_prevu"]:
                    print("        => L'OFFSET N'A PAS BOUGE : la lecture de")
                    print("           StaticBattleRules.TriggeredAbility$$GetDerivedEnvironmentAbilities")
                    print("           est REFUTEE. Le `1` du seed venait d'ailleurs.")
        if joue == 0:
            print("      => AUCUNE variante jouee : contre-epreuve NON CONFRONTEE.")
            ok = False
    else:
        print("\n  10. `derived` fait varier expres ............................. NON JOUEE")
        print("      Rejouer avec --contre-derived : sans elle, `derived` n'est verifie que sur")
        print("      un seul BC, ou il ne peut pas varier -- le regime est DEGENERE.")

    print("\n  => L'ordre d'allocation est %s"
          % ("MECANIQUE : un emetteur peut le reproduire ENTIEREMENT depuis la BC plus les\n"
             "     deux tables statiques mirrorees ici -- plus aucun terme libre." if ok
             else "MIS EN DEFAUT sur au moins un axe -- lire le detail ci-dessus."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
