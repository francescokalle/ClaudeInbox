# ClaudeInbox

Canale email **per Claude Code**: permette a Claude di **notificarti** (resoconti a
fine lavori, avvisi quando lo lasci lavorare in autonomia) e — una volta completato
il setup — di **leggere le tue risposte** e replicare con un ACK conciso.

È **provider-agnostico** (qualsiasi SMTP/IMAP: Scaleway, Gmail, Mailgun,
self-hosted…), **self-hosted** (gira sul tuo PC, le credenziali restano tue) e a
**zero dipendenze** (solo Python 3, nessun `pip install`).

| Funzione | Comando | Serve |
| --- | --- | --- |
| **Invio** notifiche/resoconti | `claude_mail.py send` | SMTP |
| **Lettura** risposte | `claude_mail.py fetch` | IMAP (casella dedicata) |
| **Loop** ACK+domande automatico | `reply_loop.py` | IMAP + CLI `claude` |
| **Setup** guidato nel browser | `setup_web.py` | — |

## Setup in 2 minuti

```bash
git clone <questo-repo> ClaudeInbox && cd ClaudeInbox
python3 bin/setup_web.py            # apre http://127.0.0.1:8765
```

Nel wizard: inserisci mittente/destinatario e i dati SMTP, premi **Testa SMTP** e
**Invia mail di prova**, poi **Salva**. Fatto: da qualsiasi sessione Claude Code
potrai far inviare notifiche. L'IMAP (lettura risposte) è opzionale e configurabile
dopo.

> In alternativa al wizard: copia `.env.example` in `~/.claude/claude-mail.env`
> (`chmod 600`) e compilalo a mano.

## Come funziona

```
                 send                        risponde a
  Claude Code ─────────▶  MAIL_SENDER  ─────────▶  MAIL_RECIPIENT (tu)
     │          (SMTP)         │          (tu)            │
     │                         │  inoltro (es. Cloudflare)│
     │                         ▼                          │
     │               casella IMAP dedicata  ◀─────────────┘
     │      fetch          (a Claude)
     └──────◀────────────────────┘
        reply_loop.py → claude -p → ACK breve + domande → send
```

1. **Invio** — `send` spedisce da `MAIL_SENDER` a `MAIL_RECIPIENT` via SMTP
   (STARTTLS o SSL secondo config).
2. **Risposta** — la tua risposta torna a `MAIL_SENDER`; instradala verso una
   **casella IMAP dedicata a Claude** (es. regola di forwarding sul tuo provider /
   Cloudflare Email Routing).
3. **Lettura** — `fetch` legge i messaggi **non letti** (UNSEEN) da quella casella.
4. **Loop** — `reply_loop.py` (via cron) invoca `claude -p`: Claude manda **una
   sola** email con un **ACK breve** di cosa ha capito + eventuali **domande**, e
   nulla più (mai il re-dump dell'output). Le risposte restano nello stesso thread.

## Componenti

- **`bin/setup_web.py`** — wizard locale (solo `127.0.0.1`) per configurare, testare
  SMTP/IMAP, inviare una mail di prova e salvare l'env con `chmod 600`.
- **`bin/claude_mail.py`** — CLI email (stdlib):
  - `send "Oggetto" "Corpo"` — invia; il corpo può arrivare da **stdin**; opzione
    `--in-reply-to "<msgid>"` per il threading.
  - `fetch [n]` — stampa le ultime `n` risposte **non lette** (default 5; corpo
    troncato a 4000 caratteri); include il `Message-ID` per il threading.
- **`bin/reply_loop.py`** — un giro del loop: se l'IMAP è configurato delega la
  risposta a `claude -p`; altrimenti **esce senza fare nulla** (sicuro da
  schedulare anche prima del setup).

## Configurazione

File in `~/.claude/claude-mail.env` (`chmod 600`, **fuori dal repo**). Percorso
sovrascrivibile con la variabile `CLAUDEINBOX_ENV`. Vedi `.env.example`.

```ini
# Invio (SMTP)
SMTP_HOST=smtp.provider.com
SMTP_PORT=587            # 587=STARTTLS, 465=SSL
SMTP_SECURITY=starttls   # starttls | ssl | (vuoto = dedotto dalla porta)
SMTP_LOGIN=...
SMTP_PASSWORD=...
# Indirizzi
MAIL_SENDER=claude@tuo-dominio.com
MAIL_RECIPIENT=tu@tuo-dominio.com
# Lettura risposte (IMAP) — opzionale, casella DEDICATA
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=...
IMAP_PASSWORD=...
```

## Uso manuale

```bash
python3 bin/claude_mail.py send "Oggetto" "Corpo"
echo "corpo lungo…" | python3 bin/claude_mail.py send "Oggetto"   # da stdin
python3 bin/claude_mail.py fetch          # ultime 5 risposte non lette (serve IMAP)
python3 bin/claude_mail.py fetch 20
```

### Quando Claude usa questo strumento
Solo se **lo chiedi** o quando lasci un **task autonomo** / dici che vai via: in tal
caso Claude invia un resoconto a fine lavori. **Niente spam.**

## Attivare il loop automatico (dopo il setup IMAP)

Esegui periodicamente `bin/reply_loop.py`, es. cron ogni 10 minuti:

```cron
*/10 * * * * cd ~/Documenti/ClaudeInbox && /usr/bin/python3 bin/reply_loop.py >> /tmp/claudeinbox.log 2>&1
```

Il loop invoca Claude solo se ci sono nuove risposte; Claude si limita a leggere e
rispondere via email (ACK + domande), niente altro.

## Setup della casella di lettura (una tantum)

La lettura **non** usa la tua posta personale. Serve una **casella dedicata a
Claude**:

1. Crea una casella dedicata (es. una Gmail nuova), attiva **IMAP** e genera una
   **app password**.
2. Instrada le risposte a `MAIL_SENDER` verso quella casella (regola di forwarding
   del provider, oppure **Cloudflare → Email Routing**).
3. Compila i campi `IMAP_*` nel wizard (o nell'env) e premi **Testa IMAP**.

## Troubleshooting

- **`Credenziali SMTP mancanti`** — mancano `SMTP_LOGIN`/`SMTP_PASSWORD`; controlla
  il percorso `~/.claude/claude-mail.env` (o `CLAUDEINBOX_ENV`).
- **`IMAP non configurato`** — i campi `IMAP_*` sono vuoti: completa il setup di
  lettura.
- **`fetch` non trova nulla** — legge solo i messaggi **UNSEEN** in `INBOX`; se li
  hai già aperti nella webmail risultano letti. Verifica anche la regola di
  inoltro verso la casella dedicata.
- **`reply_loop.py`: “CLI claude non trovata”** — assicurati che `claude` sia nel
  `PATH` dell'ambiente in cui gira il cron.

## Sicurezza

- I segreti stanno **fuori dal repo** (`~/.claude/claude-mail.env`, `chmod 600`);
  `.gitignore` esclude comunque `.env*`, log e cache.
- Il wizard gira **solo su `127.0.0.1`**: non è esposto in rete.
- La lettura passa solo dalla casella **dedicata** a Claude: mai riusare
  credenziali personali non autorizzate né accedere a caselle personali.
