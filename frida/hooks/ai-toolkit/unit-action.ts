// Layout offsets for the AI / battle-logic data structures the game uses
// across every action generator and bucket. None of these are
// build-specific — they're a function of the C# class shape, which has
// been stable across Tacticus updates.
//
// Generic for any AI fix that walks a Bucket<UnitAction>, reads the
// destination tile of a yielded UnitAction, or scans a List<T> field.

/** BucketAction<T> layout (gshared, T = ref type). */
export const BA_CONTENT = 0x10;  // T pointer (usually a UnitAction*)
export const BA_UTILITY = 0x18;  // Fix64 raw int64 — the score

/** UnitAction layout. The Position field is a UnitPosition struct (single
 * field `Tiles: IList<IEntity>` at +0x0), passed by value, so reading
 * UnitAction at +0x10 returns the Tiles list pointer directly. */
export const UA_POSITION = 0x10;

/** UtilityMovementCase layout — used by UtilityDecider as the per-move
 * candidate the AI scores against UtilityMovement-family utilities. */
export const UMC = {
    unit: 0x10,             // Unit (IEntity*)
    movementPosition: 0x18, // UnitPosition (struct, Tiles ptr at +0x0)
};

/** BaseUtility instance fields — TriggeredAbilitiesNonOwnerUtility and
 * other utilities extend it. Used to reach the active IMatchState via
 * the utility's State backing field. */
export const BU_STATE = 0x10;

/** UnitFootComponent — anchors a unit to its current tile. */
export const UF_UNIT_ID = 0x10;
export const UF_TILE_ID = 0x14;

/** List<T> internal layout (Mono/IL2CPP managed array backing). */
export const LIST_ITEMS_PTR = 0x10;
/** First element offset within the items[] managed array (after the
 * IL2CPP object header + length). */
export const LIST_ITEMS_BASE = 0x20;
