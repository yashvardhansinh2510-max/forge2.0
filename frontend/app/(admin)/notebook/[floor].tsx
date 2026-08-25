import { useLocalSearchParams } from "expo-router";

import WalkInsScreen from "../walkins";

/** Kitchen and Furniture deliberately share the established Walk-ins layout.
 * The route remains stable for bookmarks, but its data source is hard-pinned
 * to the floor represented by the URL. */
export default function FloorWalkIns() {
  const { floor } = useLocalSearchParams<{ floor?: string }>();
  const isFurniture = floor === "furniture";
  return <WalkInsScreen fixedFloorId={isFurniture ? "third-floor" : "second-floor"} title={isFurniture ? "Furniture Walk-ins" : "Kitchen Walk-ins"} enableQuotationTransfer />;
}
