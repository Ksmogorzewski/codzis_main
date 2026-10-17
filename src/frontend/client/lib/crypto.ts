// PKCE (RFC 7636) i odczyt JWT - bez zależności, działa w przeglądarce i w Node (testy)

export function base64url(bytes: Uint8Array): string {
  let s = "";
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export const randomString = (byteLength: number) => base64url(crypto.getRandomValues(new Uint8Array(byteLength)));

export async function pkceChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

// Payload JWT bez weryfikacji podpisu (tylko do wyświetlenia; podpis sprawdza API Gateway)
export function decodeJwt<T = Record<string, unknown>>(token: string): T | null {
  try {
    const b64 = token.split(".")[1]!.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes)) as T; // UTF-8: polskie znaki w imieniu
  } catch {
    return null;
  }
}
