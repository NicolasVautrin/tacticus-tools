/** #361 — capteur de GATE `WillBeKill` : ce que le natif APPELLE, et ce qu'il en REND.
 *
 *  ⚠ INERTE tant que le bundle n'est pas rebuildé + réinjecté (geste orchestrateur).
 *
 *  # Pourquoi ce capteur
 *
 *  `#353-r1` volet (b) : les batchs 3/4 (EXPLOSION) de
 *  `IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` n'apparaissent sur
 *  AUCUN montage. Cinq causes ont été éliminées, chacune par une mesure ou une lecture :
 *
 *   1. `CannotBeGuaranteedKilled` — RE #372 (unique écrivain `PredictNormalAttack`), et mesuré 0.
 *   2. « la borne par défaut ne suffit pas » — mesuré (`willKillDmg = 104` contre `hpBefore = 1`).
 *   3. `BlockScenarios` non vide sous les PV — mesuré `blockScenarioCount = 0` (capteur #372).
 *   4. « le pool de tuiles est vide » — ÉCARTÉ : `RammingSpeedAbility$$GetDynamicInvalidTargetReason`
 *      évalue le MÊME arbre (`SelectTile(GetTileToMoveTo())`) dans un contexte qu'il construit
 *      lui-même — `memset(ctx, 0, 0x128)` puis SEULEMENT `+0x08 = caster`, `+0x10 = target`,
 *      `+0x40 = casterTiles[0]` — et refuse le cast (`0x8000000`) quand l'arbre ne rend rien. Or
 *      `ComparablePlaybook<T>$$GenerateAttackPredictions` renseigne CES TROIS champs **et
 *      davantage**. Mesuré : le cast réel PASSE et pose le caster sur la tuile du port.
 *   5. « le voisinage de la tuile d'arrivée est vide » — mesuré : 1 ami + 2 ennemis adjacents.
 *
 *  Et `get_WillBeKill` FONCTIONNE : `StormOfFlensingBladesPlaybook$$MakeDamagePredictions` rend
 *  `new[]{ev, ev}` quand le flag est faux et un tableau VIDE quand il est vrai — mesuré 2 puis 0.
 *
 *  Il reste donc UN maillon jamais instrumenté, et un seul : ce que
 *  `System.Linq.Enumerable$$Any<T>(selfPreds, RammingSpeedPlaybook.<>c$$<MakeDamagePredictions>b__2_0)`
 *  fait du prédicat. Le capteur #372 lit `get_WillBeKill` sur l'event RENDU ; personne n'a lu ce
 *  que le NATIF appelle.
 *
 *  # Ce que ce capteur mesure, et pourquoi c'est le bon point d'ancrage
 *
 *  Il intercepte `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` — le foyer
 *  UNIQUE du prédicat, quel que soit le chemin (appel direct, lambda LINQ, sélecteur de tri) —
 *  le temps d'UNE invocation RPC, et enregistre par appel : le `this`, le verdict RENDU par le
 *  natif, et les entrées décodées du même objet. Trois issues, toutes discriminantes :
 *
 *   * **0 appel**   → `Any` n'invoque même pas le prédicat (la liste qu'il itère est vide côté
 *                     natif, alors que la liste rendue contient l'event) ;
 *   * **rend true** → la gate OUVRE ; la cause est en AVAL (l'évaluation des sélecteurs des
 *                     batchs 3/4, dans un contexte pourtant renseigné) ;
 *   * **rend false**→ le natif lit un AUTRE objet que celui que décode le capteur #372 (offset du
 *                     paramètre du lambda dans le régime fully-shared generic).
 *
 *  # Discipline
 *
 *  ⚠ `get_WillBeKill` est aussi appelé par l'UI (`idun.Ui.IdunUnitHud$$ShowPrediction`) et par les
 *  sélecteurs de tri (`SortTargetsByDamagePredictionSelector`). Le hook est donc **armé à la
 *  demande, détaché immédiatement**, et **filtré sur le thread appelant** — jamais un hook
 *  permanent, jamais un broad-hook (interdits du CLAUDE.md). Le nombre d'entrées est borné.
 *
 *  Résolution par NOM (aucune RVA) : `findClassAnywhere` + `findMethod`. Si un maillon ne résout
 *  pas, on rend une ERREUR NOMMÉE — jamais un zéro qui se lirait comme « pas d'appel ». */
import { findClassAnywhere, findMethod } from "../../il2cpp/helpers.js";
import { readDamagePredictionResult, type DamagePredictionFields } from "../../game/damage-prediction.js";

/** Un appel de `get_WillBeKill` observé pendant la fenêtre armée. `returned` est le verdict du
 *  NATIF (registre de retour), `decoded` les entrées lues sur le MÊME `this` — les confronter est
 *  tout l'intérêt : un désaccord accuse la base de lecture, un accord innocente le décodeur. */
export interface WillBeKillCall {
    /** `this` = le premier octet des champs du `DamagePredictionResult` (jamais boxé ici : le
     *  natif passe l'adresse du struct). */
    thisPtr: string;
    returned: boolean;
    decoded: DamagePredictionFields | null;
    decodeError?: string;
}

export interface WillBeKillProbe {
    /** `null` = capteur NON ARMÉ (maillon non résolu) — tri-état, jamais « zéro appel ». */
    calls: WillBeKillCall[] | null;
    error?: string;
    /** Appels vus sur un AUTRE thread (UI, tri) et volontairement écartés. */
    otherThreadCalls: number;
    /** Borne atteinte : au-delà, on ne perd que la queue, jamais le début. */
    truncated: boolean;
}

const MAX_CALLS = 64;

/** Exécute `fn` avec le capteur armé. Détache TOUJOURS (finally + `Interceptor.flush`), même si
 *  `fn` lève : un hook laissé en place sur ce symbole taxerait l'UI à chaque frame. */
export function withWillBeKillProbe<T>(fn: () => T): { result: T; probe: WillBeKillProbe } {
    const probe: WillBeKillProbe = { calls: null, otherThreadCalls: 0, truncated: false };
    const klass = findClassAnywhere("IdunBattle.Core.Services", "DamagePredictionResult");
    if (klass === null) {
        probe.error = "classe `IdunBattle.Core.Services.DamagePredictionResult` non résolue";
        return { result: fn(), probe };
    }
    const mi = findMethod(klass, "get_WillBeKill");
    if (mi === null) {
        probe.error = "`DamagePredictionResult::get_WillBeKill` non résolue sur la classe";
        return { result: fn(), probe };
    }
    const calls: WillBeKillCall[] = [];
    probe.calls = calls;
    const tid = Process.getCurrentThreadId();
    let pending: NativePointer | null = null;

    const listener = Interceptor.attach(mi.ptr, {
        onEnter(this: InvocationContext, args) {
            if (this.threadId !== tid) { pending = null; probe.otherThreadCalls++; return; }
            pending = args[0];
        },
        onLeave(this: InvocationContext, retval) {
            if (this.threadId !== tid || pending === null) return;
            const self = pending;
            pending = null;
            if (calls.length >= MAX_CALLS) { probe.truncated = true; return; }
            const row: WillBeKillCall = {
                thisPtr: self.toString(),
                // Le natif rend le booléen dans le registre bas ; `& 1` isole le bit sans
                // dépendre des octets hauts (que `get_WillBeKill` laisse tels quels sur la
                // branche `CannotBeGuaranteedKilled`).
                returned: (retval.toInt32() & 1) === 1,
                decoded: null,
            };
            try { row.decoded = readDamagePredictionResult(self); }
            catch (e) { row.decodeError = (e as Error).message; }
            calls.push(row);
        },
    });
    try {
        return { result: fn(), probe };
    } finally {
        listener.detach();
        Interceptor.flush();
    }
}
