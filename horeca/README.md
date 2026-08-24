# Migrazione bot Ho.Re.Ca. su Aruba

Questa cartella contiene il nuovo runtime PHP/MySQL destinato a
`https://www.raiseyourbar.it/horeca/`. La versione Railway resta il sistema di
produzione finché il collaudo e il passaggio del webhook non sono completati.

## Stato

- schema MySQL compatibile con i dati SQLite correnti;
- endpoint di salute con verifica database;
- webhook protetto dal secret token Telegram;
- deduplicazione degli update Telegram;
- primi comandi `/start`, `/help` e `/regole`;
- nessun token o password incluso nel repository.

## Configurazione staging Aruba

1. Importare `database/schema.sql` in un database MySQL vuoto.
2. Copiare `config/config.example.php` in `config/local.php` e compilare i
   valori direttamente su Aruba.
3. Eseguire `php tests/smoke.php` e il lint `php -l` su tutti i file PHP.
4. Verificare `api/health.php` e `api/telegram-webhook.php` via HTTPS.
5. Usare un bot di prova o update firmati per il collaudo. Non impostare ancora
   il webhook del bot di produzione.

Il file `config/local.php` è escluso da Git e la cartella `config` è bloccata
da `.htaccess`.

