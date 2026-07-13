// Customer Portal — shared "fetch a PDF with the customer's bearer token and
// open it" helper. Used by the Dashboard, Quotations List, and Quotation
// Detail screens so there is exactly ONE implementation of this fetch/blob/
// open dance instead of copy-pasting it per screen.
import { Linking, Platform } from "react-native";

import { api, getToken } from "@/src/api/client";
import { toast } from "@/src/components/Toast";

/**
 * @param path server path under /api, e.g. `/quotations/{id}/portal-pdf`
 * @param fallbackName used only as a hint; the server's Content-Disposition
 *        filename is what browsers/apps actually show when saving.
 */
export async function openPortalPdf(path: string, fallbackName = "quotation.pdf"): Promise<void> {
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
      toast.show(res.status === 404 ? "That PDF isn't available" : "Couldn't open the PDF");
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
    toast.show("Couldn't open the PDF — check your connection");
  }
}
