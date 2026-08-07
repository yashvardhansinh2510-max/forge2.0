// Shared "fetch an authenticated file from the API and open/save it" helper.
// Used by BOTH the customer portal (PDFs) and staff Settings (catalog
// export/backup) so there is exactly ONE implementation of this fetch/blob/
// open dance in the whole app instead of one per screen.
import { Linking, Platform } from "react-native";

import { api, getToken } from "@/src/api/client";
import { toast } from "@/src/components/Toast";

async function fetchApiBlob(path: string, errorLabel: string): Promise<Blob | null> {
  const token = await getToken();
  if (!token) {
    toast.show("Please sign in again");
    return null;
  }
  try {
    const res = await fetch(`${api.base}/api${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      toast.show(res.status === 404 ? `That ${errorLabel} isn't available` : `Couldn't download the ${errorLabel}`);
      return null;
    }
    return await res.blob();
  } catch {
    toast.show(`Couldn't download the ${errorLabel} — check your connection`);
    return null;
  }
}

// Download an authenticated file UNDER A SPECIFIC FILENAME (the tiles
// documents must save as "<Customer Name> <DD-MM-YYYY>.pdf", never
// "quotation.pdf") — window.open() ignores Content-Disposition for blob:
// URLs, so web uses an <a download> click instead. Native opens the file
// (the OS viewer's share sheet keeps the server-supplied name).
export async function downloadApiFile(path: string, filename: string, errorLabel = "file"): Promise<boolean> {
  if (Platform.OS !== "web") {
    await openApiFile(path, errorLabel);
    return true;
  }
  const blob = await fetchApiBlob(path, errorLabel);
  if (!blob) return false;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return true;
}

// Print an authenticated PDF: web renders it into a hidden iframe and calls
// print() so the browser's print dialog opens directly on the document;
// native falls back to opening the PDF (the OS viewer offers Print).
export async function printApiFile(path: string, errorLabel = "file"): Promise<void> {
  if (Platform.OS !== "web") {
    await openApiFile(path, errorLabel);
    return;
  }
  const blob = await fetchApiBlob(path, errorLabel);
  if (!blob) return;
  const url = URL.createObjectURL(blob);
  const frame = document.createElement("iframe");
  frame.style.position = "fixed";
  frame.style.right = "0";
  frame.style.bottom = "0";
  frame.style.width = "0";
  frame.style.height = "0";
  frame.style.border = "0";
  frame.src = url;
  frame.onload = () => {
    try {
      frame.contentWindow?.focus();
      frame.contentWindow?.print();
    } catch {
      window.open(url, "_blank");
    }
  };
  document.body.appendChild(frame);
  // Give the print dialog ample time before tearing the frame down.
  setTimeout(() => { frame.remove(); URL.revokeObjectURL(url); }, 120_000);
}

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
