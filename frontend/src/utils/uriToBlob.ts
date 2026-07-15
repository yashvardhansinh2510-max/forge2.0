// Shared cross-platform helper for turning an Expo ImagePicker/DocumentPicker
// `uri` into a real Blob before handing it to FormData.
//
// react-native-web has no FormData polyfill of its own — it's the browser's
// native FormData, which (per the Web spec) only accepts a real Blob/File as
// the second argument to .append(). The `{uri, name, type}` shorthand that
// native RN/Expo's FormData understands throws
// `TypeError: parameter 2 is not of type 'Blob'` on web and the upload never
// leaves the device. `fetch(uri).blob()` works identically on native too
// (Expo's picker uris are fetchable file:// / content:// URIs there), so
// there's no need to branch per-platform — always convert.
export async function uriToBlob(uri: string): Promise<Blob> {
  const res = await fetch(uri);
  return await res.blob();
}
