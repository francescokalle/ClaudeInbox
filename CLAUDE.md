# ClaudeInbox — istruzioni di progetto (per gli agenti)

Progetto **separato e globale** per la posta di Claude Code verso il proprietario
di `francescocallegaro.com`. Invio già funzionante; lettura risposte da attivare.

**Se stai riprendendo questo lavoro, leggi prima `HANDOFF.md`.**

## Regole
- **Invio email**: usa `bin/claude_mail.py send "Oggetto" "Corpo"`. Mittente
  `claude.code@francescocallegaro.com`, destinatario `mail@francescocallegaro.com`.
  Invia SOLO se l'utente lo chiede o quando lascia un task autonomo / dice che va
  via (resoconto a fine lavori). Niente spam.
- **Lettura risposte**: `bin/claude_mail.py fetch` (richiede IMAP configurato su una
  casella DEDICATA a Claude — MAI la gmail personale dell'utente).
- **Loop di risposta** (`bin/reply_loop.py`): quando arriva una risposta, Claude
  fa un **ACK breve** di cosa ha capito + eventuali **domande**, e le invia. Nient'altro.
- **Credenziali**: in `~/.claude/claude-mail.env` (fuori dal repo, chmod 600). NON
  committare segreti.
- **Sicurezza**: non usare credenziali non chiaramente autorizzate; non accedere a
  caselle personali.
