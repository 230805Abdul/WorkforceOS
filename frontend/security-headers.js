// HTTP security headers for the FRONTEND (the HTML, JavaScript and CSS files). The API sets its own, stricter ones.
// Used by `npm run dev` and `npm run preview` (vite.config.js); production hosting (Phase 5) must send the same
// PRODUCTION set, see docs/SECURITY.md, "Security headers".

const common = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "accelerometer=(), browsing-topics=(), camera=(), display-capture=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
  "Cross-Origin-Opener-Policy": "same-origin",
};

// Built app: only our own files may run or load. No inline scripts or styles, no other sites, no framing.
// (React sets element styles through the DOM API, which CSP allows; the theme script is an external file.)
export const productionCsp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

// Development server only: Vite injects inline scripts (React Fast Refresh) and <style> tags, and uses a WebSocket
// for live reload. Everything else stays as strict as production.
export const developmentCsp = productionCsp
  .replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")
  .replace("style-src 'self'", "style-src 'self' 'unsafe-inline'")
  .replace("connect-src 'self'", "connect-src 'self' ws: wss:");

export const productionHeaders = { ...common, "Content-Security-Policy": productionCsp };
export const developmentHeaders = { ...common, "Content-Security-Policy": developmentCsp };
