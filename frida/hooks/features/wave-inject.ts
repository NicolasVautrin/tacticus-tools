// wave-inject — poser des unités dans la VAGUE d'un joueur VIVANT.
//
// POURQUOI CE MODULE EXISTE, ET POURQUOI IL NE TOUCHE PAS LA BC.
// `BC.UnitSpawningOverTime.Tiers` n'est lu qu'UNE fois : `OperationProcessor$$AddPlayer(
// playerId, teamId, name, draftings, spawnsPerTurn: Dictionary<Int32, Wave>, ...)` transcrit
// le calendrier dans le `PlayerComponent` au moment où le joueur est créé, c'est-à-dire au
// SETUP. Muter la BC après — pendant le déploiement, par exemple — n'a donc AUCUN effet :
// l'objet lu n'est plus celui que le moteur consulte.
//
// Le composant, lui, expose ses propres mutateurs, et c'est par eux qu'on passe :
//     IdunBattle.Entities.Components.PlayerComponent$$AddOrCreateWave(turn: Int32)
//     IdunBattle.Entities.Components.PlayerComponent$$AddUnitForCompleteWave(
//         turn: Int32, unitToSpawn: UnitSpawningOverTimeConfiguration.UnitToSpawn)
// Ce sont des méthodes DU JEU appliquées à un état vivant, pas une écriture fabriquée.
//
// ⚠ AUCUN TYPE VALEUR ICI, et c'est ce qui rend le geste sûr. Mesuré sur `classes.tsv` :
// `UnitToSpawn` (40 o), `Wave` (64 o) et `UnitSpawningOverTimeConfiguration` (32 o) ont tous
// `System.Object` pour parent, et la clé du dictionnaire de vagues est un `System.Int32`.
// Le crash de clé boxée du 2026-08-21 (dump `Tacticus.exe.30620.dmp`) ne peut pas se
// reproduire par ce chemin — contrairement à `EnvironmentAbilities.AbilitiesConfigurations`.
//
// ⚠ `AddUnitForCompleteWave` ALIMENTE `ToSpawnOnComplete`, PAS `ToSpawn`. La cadence n'est
// donc pas « à chaque tour » mais « quand la vague est nettoyée, la suivante arrive » —
// c'est `VerifyCompleteWaveOperation$$SpawnCompleteUnits` qui la joue, après
// `IsWaveComplete`. Une BC, elle, sait exprimer les deux ; ce module n'en couvre qu'une.

import {
    class_get_name, class_get_nested_types, findClassAnywhere, findMethodByParamCount,
    getFieldOffset, s,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { deserializeFromJson, isDeserializerReady } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { runnerOff } from "../game/runner.js";
import { getRunner } from "../game/runner-registry.js";
import {
    EntityType, forEachComponent, forEachEntity, playerComponentClass,
} from "../game/match-state.js";
import { estRefus, refus } from "./lecture-champs.js";
import { Refus } from "./view-command.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

// ⚠ LES DEUX RPC PASSENT PAR `queueOnMainThread`, ET CE N'EST PAS FACULTATIF.
// Un RPC Frida arrive sur un thread A LUI ; tout `invokeMethod` doit s'exécuter sur le thread
// principal d'Unity. Mesuré le 2026-08-22 (dump `Tacticus.exe.21864.dmp`) : `waveState`, qui
// ne fait que LIRE, a survécu -- et c'est précisément ce qui rend le piège vicieux, parce
// qu'il donne l'impression que le chemin est sain. `waveInject`, qui MUTE le dictionnaire de
// vagues du `PlayerComponent`, a tué le process au premier appel. La lecture qui passe ne dit
// rien de l'écriture qui suit.

/** Un `System.Int32` pour `il2cpp_runtime_invoke` : un POINTEUR VERS la valeur, jamais la
 *  valeur déguisée en pointeur.
 *
 *  ⚠ `runtime_invoke` prend un `void**` et DÉRÉFÉRENCE chaque argument de type valeur. Passer
 *  `ptr(1)` lui fait donc lire l'adresse 1 — ça ne lève pas, ça TUE le process. Mesuré le
 *  2026-08-22 (dump `Tacticus.exe.36184.dmp`) : trois sites de ce module écrits ainsi, la
 *  session est morte au PREMIER appel, avant même toute écriture. */
function argInt(v: number): NativePointer {
    return Memory.alloc(4).writeS32(v);
}

const NS_CFG = "IdunBattle.Configuration";
const NS_COMP = "IdunBattle.Entities.Components";

/** `UnitSpawningOverTimeConfiguration.UnitToSpawn` — classe IMBRIQUÉE, donc introuvable par
 *  `findClassAnywhere` sous son nom simple. On énumère les types imbriqués de l'englobante.
 *
 *  ⚠ Résolue à CHAQUE appel, jamais mise en cache : ce module est appelé une poignée de fois
 *  par bataille, et un cache survivrait à un changement de build sans le dire. */
function classeUnitToSpawn(): NativePointer | Refus {
    const kOuter = findClassAnywhere(NS_CFG, "UnitSpawningOverTimeConfiguration");
    if (!kOuter) {
        return refus("classe `" + NS_CFG + ".UnitSpawningOverTimeConfiguration` introuvable "
            + "-- chemin PÉRIMÉ sur ce build");
    }
    const it = Memory.alloc(Process.pointerSize);
    it.writePointer(ptr(0));
    let n: NativePointer;
    const vus: string[] = [];
    while (!(n = class_get_nested_types(kOuter, it) as NativePointer).isNull()) {
        let nom: string;
        try { nom = s(class_get_name(n) as NativePointer); } catch { continue; }
        vus.push(nom);
        if (nom === "UnitToSpawn") return n;
    }
    return refus("type imbriqué `UnitToSpawn` ABSENT de "
        + "`UnitSpawningOverTimeConfiguration` -- imbriqués vus : " + JSON.stringify(vus));
}

/** Un `UnitToSpawn` rempli, par le DÉSÉRIALISEUR du jeu.
 *
 *  ⚠ Pas de construction champ par champ : la forme exacte est celle qu'on a LUE dans une BC
 *  que le jeu a lui-même sérialisée (`logs/sandbox-bc-waves-*.json`), donc on la lui rend
 *  telle quelle et Newtonsoft fait le reste. Écrire les 40 octets à la main supposerait des
 *  offsets, et un offset faux ne se signale pas — il rend un objet plausible. */
function creerUnitToSpawn(
    unitId: string, spawnPointTag: string, spawnSource: number,
): NativePointer | Refus {
    if (!isDeserializerReady()) {
        return refus("`JsonConvert.DeserializeObject` non résolu -- `UnitToSpawn` ne peut pas "
            + "être construit sans lui, et je ne le fabrique pas à la main");
    }
    const k = classeUnitToSpawn();
    if (estRefus(k)) return k;
    const json = JSON.stringify({
        SpawnPointTag: spawnPointTag, UnitId: unitId,
        SpawnSource: spawnSource, IsClone: false,
    });
    let o: NativePointer;
    try { o = deserializeFromJson(json, k as NativePointer); }
    catch (e) { return refus("désérialisation d'`UnitToSpawn` : " + (e as Error).message); }
    if (o.isNull()) return refus("`UnitToSpawn` désérialisé en NUL");
    gcRoot.add(o);
    return o;
}

/** L'offset de `PlayerComponent.TeamId`, résolu PAR NOM (deux écritures possibles selon que
 *  le champ est une auto-propriété ou non). Un offset en dur rendrait un entier plausible. */
function offsetTeamId(): number | Refus {
    if (!playerComponentClass) return refus("classe `PlayerComponent` non résolue");
    for (const nom of ["TeamId", "<TeamId>k__BackingField"]) {
        const off = getFieldOffset(playerComponentClass, nom);
        if (off >= 0) return off;
    }
    return refus("`PlayerComponent.TeamId` ABSENT sous ses deux écritures connues "
        + "-- chemin PÉRIMÉ");
}

// --- LE COMPTEUR DE TIRS ------------------------------------------------------------------
//
// ⚠ POURQUOI UN COMPTEUR ET PAS UN XREF. `VerifyCompleteWaveOperation$$Execute` n'a qu'UN
// appelant, `OperationProcessor$$VerifyCompleteWave` -- lequel n'a AUCUN xref de code, rien
// que des entrées DATA : il est appelé par dispatch d'interface (`IOperationProcessor`).
// Savoir s'il tourne dans une bataille ordinaire ne se lit donc pas, ça se COMPTE.
//
// Ancrage PASSIF (`Interceptor.attach`, aucun `replace`), sur une méthode FROIDE : elle ne
// peut tirer qu'une fois par tour et par joueur. Armé à la demande, jamais au register.
let verifTirs = 0;
let verifArme: InvocationListener | null = null;

function armerCompteur(): true | Refus {
    if (verifArme) return true;
    const k = findClassAnywhere("IdunBattle.Operations", "VerifyCompleteWaveOperation");
    if (!k) return refus("classe `VerifyCompleteWaveOperation` introuvable");
    const m = findMethodByParamCount(k, "Execute", 0);
    if (!m || m.ptr.isNull()) {
        return refus("`VerifyCompleteWaveOperation$$Execute()` non résolue -- chemin PÉRIMÉ");
    }
    verifArme = Interceptor.attach(m.ptr, { onEnter() { verifTirs++; } });
    return true;
}

interface Joueur { entite: NativePointer; comp: NativePointer; teamId: number; }

/** Tous les joueurs de l'état, avec leur `PlayerComponent` et leur `TeamId`. */
function joueurs(statePtr: NativePointer): Joueur[] | Refus {
    const off = offsetTeamId();
    if (estRefus(off)) return off;
    const out: Joueur[] = [];
    forEachEntity(statePtr, (e, _id, ty) => {
        if (ty !== EntityType.Player) return;
        forEachComponent(e, (comp, klass) => {
            if (!playerComponentClass || !klass.equals(playerComponentClass)) return;
            let t: number;
            try { t = comp.add(off as number).readS32(); } catch { return; }
            out.push({ entite: e, comp, teamId: t });
        });
    });
    return out;
}

/** L'état vivant d'un runner. */
function etatDuRunner(runnerId: unknown): NativePointer | Refus {
    if (typeof runnerId !== "number") {
        return refus("`runnerId` manquant -- ce module n'a PAS de repli sur « le runner "
            + "courant » : viser le mauvais match écrirait dans la bataille d'un autre");
    }
    let runner: NativePointer;
    try { runner = getRunner(runnerId).runner; }
    catch (e) { return refus("runner " + runnerId + " : " + (e as Error).message); }
    const p = runner.add(runnerOff.state).readPointer();
    if (p.isNull()) return refus("runner " + runnerId + " : `state` NUL");
    return p;
}

export function register(ctx: Ctx): void {
    /** LECTURE SEULE — qui sont les joueurs, et quelle vague porte tel tour.
     *  À jouer AVANT et APRÈS toute injection : c'est la mesure, l'injection n'est que le geste.
     *  body: { runnerId, turn? } */
    ctx.rpc.waveState = (
        body?: { runnerId?: number; turn?: number; armer?: boolean },
    ) => queueOnMainThread(() => {
        if (body?.armer) {
            const a = armerCompteur();
            if (estRefus(a)) return { ok: false, error: a.error };
        }
        const st = etatDuRunner(body?.runnerId);
        if (estRefus(st)) return { ok: false, error: st.error };
        const js = joueurs(st as NativePointer);
        if (estRefus(js)) return { ok: false, error: js.error };

        // ⚠ LECTURES BRUTES, AUCUN `invokeMethod`. La version precedente appelait
        // `GetWaveTurn` et lisait son retour comme un entier -- or `runtime_invoke` BOXE les
        // types valeur, donc elle rendait un POINTEUR (mesure : -41634880, -41634912,
        // -41634944, espaces de 32 octets, soit trois boites consecutives). Le decompile
        // rend l'appel inutile : `GetWaveTurn(t) = this[+0x60] + t`, donc le decalage se LIT.
        const out = (js as Joueur[]).map((j) => {
            let decalage: number | null = null;
            let vaguesPosees: boolean | null = null;
            try { decalage = j.comp.add(0x60).readS32(); } catch { decalage = null; }
            try { vaguesPosees = !j.comp.add(0x58).readPointer().isNull(); }
            catch { vaguesPosees = null; }
            return { entite: j.entite.toString(), teamId: j.teamId, decalage, vaguesPosees };
        });
        return {
            ok: true, joueurs: out,
            verifTirs,
            verifArme: verifArme !== null,
            note: "`decalage` = PlayerComponent[+0x60] : la boucle de "
                + "`VerifyCompleteWaveForPlayer` visite les tours 0..(decalage + toursDemarres). "
                + "`verifTirs` = nombre de passages REELS dans `VerifyCompleteWaveOperation"
                + "$$Execute` -- 0 avec `verifArme: true` signifie que l'operation NE TOURNE PAS. "
                + "null = NON MESURE, jamais un zero.",
        };
    });

    /** MUTATION — ajoute `count` × `unitId` à la vague du tour `turn`, pour l'équipe `teamId`.
     *
     *  ⚠ ÉCRITURE SUR UN MATCH VIVANT. Elle s'OBSERVE : jouer `waveState` avant, puis
     *  `combatSnapshot` après pour compter les unités réellement apparues. « L'appel est
     *  passé » ne veut pas dire « les unités sont là » — c'est le piège mesuré trois fois
     *  le 2026-08-22 sur la greffe d'environnement.
     *
     *  body: { runnerId, teamId, turn, unitId, count?, spawnPointTag?, spawnSource? } */
    ctx.rpc.waveInject = (body?: {
        runnerId?: number; teamId?: number; turn?: number; unitId?: string;
        count?: number; spawnPointTag?: string; spawnSource?: number;
    }) => queueOnMainThread(() => {
        const st = etatDuRunner(body?.runnerId);
        if (estRefus(st)) return { ok: false, error: st.error };
        if (typeof body?.teamId !== "number") {
            return { ok: false, error: "`teamId` manquant (IdunBattle.Core.TeamId : "
                + "0=Environment, 1=Team1_Default, 2=Team2_DefaultEnemy, 3=Team3)" };
        }
        if (typeof body?.turn !== "number") return { ok: false, error: "`turn` manquant" };
        if (!body?.unitId) return { ok: false, error: "`unitId` manquant" };
        const count = typeof body.count === "number" ? body.count : 1;
        if (count < 1 || count > 20) {
            return { ok: false, error: "`count` hors bornes (1..20) -- borne DÉLIBÉRÉE : "
                + "au-delà on sature les tuiles libres et l'échec serait muet" };
        }

        const js = joueurs(st as NativePointer);
        if (estRefus(js)) return { ok: false, error: js.error };
        const cibles = (js as Joueur[]).filter((j) => j.teamId === body.teamId);
        if (cibles.length === 0) {
            return { ok: false, error: "aucun joueur d'équipe " + body.teamId + " dans ce match "
                + "-- équipes présentes : "
                + JSON.stringify((js as Joueur[]).map((j) => j.teamId)) };
        }
        if (cibles.length > 1) {
            return { ok: false, error: cibles.length + " joueurs partagent l'équipe "
                + body.teamId + " -- REFUS : en choisir un au hasard rendrait le montage "
                + "non reproductible" };
        }
        const cible = cibles[0];

        if (!playerComponentClass) return { ok: false, error: "classe `PlayerComponent` absente" };
        const mCreate = findMethodByParamCount(playerComponentClass, "AddOrCreateWave", 1);
        const mAdd = findMethodByParamCount(playerComponentClass, "AddUnitForCompleteWave", 2);
        if (!mCreate || !mAdd) {
            return { ok: false, error: "`AddOrCreateWave(1)`/`AddUnitForCompleteWave(2)` "
                + "INTROUVABLES sur `PlayerComponent` -- chemin PÉRIMÉ, pas de repli" };
        }

        try { invokeMethod(mCreate.info, cible.comp, [argInt(body.turn)]); }
        catch (e) { return { ok: false, error: "`AddOrCreateWave` a levé : " + (e as Error).message }; }

        const poses: string[] = [];
        for (let i = 0; i < count; i++) {
            const u = creerUnitToSpawn(body.unitId, body.spawnPointTag ?? "0",
                                       typeof body.spawnSource === "number" ? body.spawnSource : 3);
            if (estRefus(u)) {
                return { ok: false, error: "unité " + i + " : " + u.error, posees: poses.length };
            }
            try { invokeMethod(mAdd.info, cible.comp, [argInt(body.turn), u as NativePointer]); }
            catch (e) {
                return { ok: false, posees: poses.length,
                         error: "`AddUnitForCompleteWave` a levé à l'unité " + i + " : "
                             + (e as Error).message };
            }
            poses.push((u as NativePointer).toString());
        }

        return {
            ok: true, teamId: body.teamId, turn: body.turn, unitId: body.unitId,
            posees: poses.length,
            joueur: cible.entite.toString(),
            note: "ces unités alimentent `ToSpawnOnComplete` : elles arrivent quand la vague "
                + "du tour " + body.turn + " est NETTOYEE, pas au tour lui-meme. "
                + "COMPTER avec `combatSnapshot` -- l'appel passe ne prouve rien.",
        };
    });
}
