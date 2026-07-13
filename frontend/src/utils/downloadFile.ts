// Shared "fetch an authenticated file from the API and open/save it" helper.
// Used by BOTH the customer portal (PDFs) and staff Settings (catalog
// export/backup) so there is exactly ONE implementation of this fetch/blob/
// open dance in the whole app instead of one per screen.
import { Linking, Platform } from "react-native";

import { api, getToken } from "@/src/api/client";
import { toast } from "@/src/components/Toast";

export async function openApiFile(path: string, errorLabel = "file"): Promise<void> {
  const token = await getToken();
  if (!token) {
    toast.show("Please sign in again");
    return;
  }
  try {
    const res = await fetch(`${api.base}/api${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      toast.show(res.status === 404 ? `That ${errorLabel} isn't available` : `Couldn't download the ${errorLabel}`);
      return;
    }
    const blob = await res.blob();
    if (Platform.OS === "web") {
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      return;
    }
    const reader = new FileReader();
    reader.onloadend = () => Linking.openURL(reader.result as string);
    reader.readAsDataURL(blob);
  } catch {
    toast.show(`Couldn't download the ${errorLabel} — check your connection`);
  }
}
