// The public shop's security headers (ADR-103), in a module of their own: a Worker's main module
// may export only its handlers. Set at the edge on every answer, so they hold whatever answers
// (the studio, the preview's own files, the Worker's own 404s and redirects). A header the
// studio already sent is kept (it may know better: an embed's frame-ancestors). No third-party
// scripts: the shop has no analytics or tracking; the fonts come from Google Fonts until they
// are self-hosted (then drop the two Google addresses below).
export const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: blob:",
  "media-src 'self' blob:",
  "connect-src 'self'",
  "frame-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join("; ");

export const SECURITY_HEADERS: Record<string, string> = {
  "content-security-policy": CSP,
  "strict-transport-security": "max-age=31536000",
  "x-content-type-options": "nosniff",
  "x-frame-options": "SAMEORIGIN",
  "referrer-policy": "strict-origin-when-cross-origin",
  "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "cross-origin-opener-policy": "same-origin",
};

export function secure(res: Response): Response {
  const out = new Response(res.body, res); // the headers of a fetched answer are immutable
  for (const [k, v] of Object.entries(SECURITY_HEADERS))
    if (!out.headers.has(k)) out.headers.set(k, v);
  out.headers.delete("x-powered-by");
  return out;
}
