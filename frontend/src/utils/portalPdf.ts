// Customer Portal — thin wrapper over the shared openApiFile helper, kept as
// its own file/name for the 3 existing PDF-download call sites (main,
// revision, brand). See src/utils/downloadFile.ts for the actual fetch/blob/
// open implementation (also used by staff Settings > Catalog export/backup).
import { openApiFile } from "@/src/utils/downloadFile";

export async function openPortalPdf(path: string, _fallbackName = "quotation.pdf"): Promise<void> {
  return openApiFile(path, "PDF");
}

