import home from "../public/index.html";
import privacy from "../public/privacy.html";
import support from "../public/support.html";
import terms from "../public/terms.html";

const pages: Record<string, string> = { "/": home, "/privacy": privacy, "/support": support, "/terms": terms };

export function publicPage(path: string, method: string): Response | undefined {
  if ((method !== "GET" && method !== "HEAD") || !Object.hasOwn(pages, path)) return;
  return new Response(method === "HEAD" ? null : pages[path], { headers: {
    "Content-Type": "text/html; charset=utf-8",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  } });
}
