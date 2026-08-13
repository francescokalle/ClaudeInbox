/**
 * ClaudeInbox — Cloudflare Email Worker.
 *
 * Riceve le email instradate da Cloudflare Email Routing e le inoltra, come MIME
 * grezzo, al receiver self-hosted esposto tramite tunnel cloudflared
 * (es. https://inbox.francescocallegaro.com/incoming). È il ponte SMTP -> HTTP
 * che permette di ricevere posta su un server dietro CGNAT (nessuna porta 25).
 *
 * Secret da impostare (wrangler secret put ...):
 *   RECEIVER_URL    URL completo del receiver via tunnel, es.
 *                   https://inbox.francescocallegaro.com/incoming
 *   RECEIVER_TOKEN  stesso valore del RECEIVER_TOKEN del receiver
 *
 * Se il receiver non risponde 2xx, il Worker LANCIA un errore: Cloudflare
 * restituisce un fallimento temporaneo al mittente, che ritenterà più tardi
 * (così se il server casalingo è spento la mail non va persa, viene ritentata).
 */
export default {
  async email(message, env) {
    if (!env.RECEIVER_URL || !env.RECEIVER_TOKEN) {
      throw new Error("RECEIVER_URL/RECEIVER_TOKEN non configurati");
    }
    const raw = await new Response(message.raw).arrayBuffer();
    const res = await fetch(env.RECEIVER_URL, {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + env.RECEIVER_TOKEN,
        "Content-Type": "message/rfc822",
        "X-Mail-From": message.from || "",
        "X-Mail-To": message.to || "",
      },
      body: raw,
    });
    if (!res.ok) {
      // Errore -> ritento lato mittente (temporary failure).
      throw new Error("Receiver HTTP " + res.status);
    }
  },
};
