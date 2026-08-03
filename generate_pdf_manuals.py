import os
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

def create_candidate_pdf(filename):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0d47a1'),
        alignment=1,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#555555'),
        alignment=1,
        spaceAfter=15
    )

    h2_style = ParagraphStyle(
        'Heading2Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#1976d2'),
        spaceBefore=10,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#222222'),
        spaceAfter=6
    )

    cmd_style = ParagraphStyle(
        'CmdStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#0d47a1')
    )

    story = []

    # Header
    story.append(Paragraph("📖 GUIDA UFFICIALE CANDIDATI & LAVORATORI", title_style))
    story.append(Paragraph("Offerte Lavoro Bar Torino — Community Horeca (9.000+ Iscritti)", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#e0e0e0'), spaceAfter=15))

    # Section 1
    story.append(Paragraph("🎯 1. Cos'è la Community Offerte Lavoro Bar Torino", h2_style))
    story.append(Paragraph("Offerte Lavoro Bar Torino è la prima community Telegram a Torino con oltre <b>9.000 iscritti attivi</b> creata per far incontrare baristi, bartender, camerieri, cuochi, pizzaioli e titolari di locali e ristoranti.", body_style))
    story.append(Spacer(1, 10))

    # Section 2
    story.append(Paragraph("⚡ 2. Come Candidarsi alle Offerte in 1-Click", h2_style))
    story.append(Paragraph("• <b>Candidatura 1-Click</b>: Sfoglia gli annunci nel gruppo Telegram e clicca sul pulsante <i>'⚡ Candidati in 1-Click'</i>. Rispondi alle 2 domande di pre-screening ed invia subito la tua candidatura.<br/>• <b>Contatto Diretto</b>: Ogni annuncio riporta i contatti diretti del locale (Username Telegram o WhatsApp).", body_style))
    story.append(Spacer(1, 10))

    # Section 3
    story.append(Paragraph("🍸 3. Scheda Profilo & Skill Professionale", h2_style))
    story.append(Paragraph("Registra o aggiorna il tuo profilo usando il comando <b>/registrati</b> o <b>/profilo</b>. Potrai indicare i ruoli desiderati (Barista, Cameriere, Chef), le competenze (HACCP, Caffetteria, Mixology, Cassa), la disponibilità ed i quartieri preferiti di Torino.", body_style))
    story.append(Spacer(1, 10))

    # Section 4
    story.append(Paragraph("🔔 4. Notifiche PUSH Automatiche in Privato", h2_style))
    story.append(Paragraph("Quando un locale pubblicabile un annuncio prioritario nella tua zona o per il tuo ruolo, il bot ti invierà una notifica istantanea in privato per candidarti prima di tutti gli altri.", body_style))
    story.append(Spacer(1, 15))

    # Section 5: Commands Table
    story.append(Paragraph("🛠️ 5. Elenco Completo dei Comandi Telegram", h2_style))
    
    cmd_data = [
        [Paragraph("<b>Comando</b>", cmd_style), Paragraph("<b>Descrizione e Utilizzo</b>", body_style)],
        [Paragraph("<b>/registrati</b>", cmd_style), Paragraph("Compila o modifica la tua Scheda Profilo & Skill.", body_style)],
        [Paragraph("<b>/profilo</b>", cmd_style), Paragraph("Visualizza la tua scheda profilo salvata nel sistema.", body_style)],
        [Paragraph("<b>/offerte</b>", cmd_style), Paragraph("Consulta l'elenco delle ultime offerte di lavoro attive.", body_style)],
        [Paragraph("<b>/guida</b>", cmd_style), Paragraph("Apri la guida d'uso e scarica il manuale ufficiale.", body_style)],
        [Paragraph("<b>/pubblica</b>", cmd_style), Paragraph("Modulo per pubblicare annunci di lavoro Horeca.", body_style)],
        [Paragraph("<b>/mie_offerte</b>", cmd_style), Paragraph("Gestisci e modifica le tue offerte pubblicate.", body_style)],
        [Paragraph("<b>/evidenza</b>", cmd_style), Paragraph("Info su pacchetti promozionali in evidenza e VIP.", body_style)],
        [Paragraph("<b>/regole</b>", cmd_style), Paragraph("Leggi il regolamento ufficiale della community.", body_style)],
        [Paragraph("<b>/stats</b>", cmd_style), Paragraph("Guarda le statistiche aggiornate del gruppo.", body_style)],
        [Paragraph("<b>/start</b>", cmd_style), Paragraph("Riavvia il bot e mostra il menu principale.", body_style)]
    ]

    table = Table(cmd_data, colWidths=[110, 410])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e3f2fd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0d47a1')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bbdefb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fbfd')])
    ]))

    story.append(table)
    doc.build(story)
    print(f"✅ Creato PDF Candidati: {filename}")


def create_employer_pdf(filename):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#2e7d32'),
        alignment=1,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#555555'),
        alignment=1,
        spaceAfter=15
    )

    h2_style = ParagraphStyle(
        'Heading2Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#2e7d32'),
        spaceBefore=10,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#222222'),
        spaceAfter=6
    )

    cmd_style = ParagraphStyle(
        'CmdStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#2e7d32')
    )

    story = []

    # Header
    story.append(Paragraph("🏪 GUIDA DATORI DI LAVORO & TITOLARI", title_style))
    story.append(Paragraph("Offerte Lavoro Bar Torino — Guida alla Selezione Personale", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#e0e0e0'), spaceAfter=15))

    # Section 1
    story.append(Paragraph("📢 1. Pubblica un'Offerta di Lavoro", h2_style))
    story.append(Paragraph("Digita il comando <b>/pubblica</b> col bot ed inserisci i dettagli del locale (Nome, Ruolo cercato, Zona, Paga, Contatti). Puoi scegliere tra 4 livelli di visibilità:<br/>• 🆓 <b>Annuncio Gratuito (0€)</b>: Pubblicazione standard nel gruppo.<br/>• ⭐ <b>In Evidenza 24h (5,39€ / 250 Stelle)</b>: Post 🔝 + Pin 24h + Push istantanea.<br/>• 👑 <b>Sponsor VIP 7 Giorni (10,90€ / 500 Stelle)</b>: Pin 7 giorni + Multi-push.<br/>• 💎 <b>Pass VIP Mensile (29,90€ / 1.400 Stelle)</b>: Pin 30 giorni + Annunci illimitati per 1 mese + Push prioritario.", body_style))
    story.append(Spacer(1, 10))

    # Section 2
    story.append(Paragraph("📊 2. Dashboard Candidati & Filtri Avanzati", h2_style))
    story.append(Paragraph("Con i pacchetti Evidenza e VIP sblocchi la Dashboard Candidati: una Mini-App riservata che ti mostra l'elenco dei candidati profilati a Torino con filtri per competenze (Caffetteria, Mixology, HACCP, Lingue) e contatto 1-Click via Telegram o WhatsApp.", body_style))
    story.append(Spacer(1, 10))

    # Section 3
    story.append(Paragraph("✏️ 3. Sincronizzazione ed Editing Annunci", h2_style))
    story.append(Paragraph("Usa il comando <b>/mie_offerte</b> per aggiornare i dati dei tuoi annunci in qualsiasi momento: la modifica aggiornerà istantaneamente anche il post nel gruppo Telegram!", body_style))
    story.append(Spacer(1, 15))

    # Section 4: Commands Table
    story.append(Paragraph("🛠️ 4. Elenco Completo dei Comandi Telegram", h2_style))

    cmd_data = [
        [Paragraph("<b>Comando</b>", cmd_style), Paragraph("<b>Descrizione e Utilizzo</b>", body_style)],
        [Paragraph("<b>/pubblica</b>", cmd_style), Paragraph("Apre il modulo di compilazione e pubblicazione offerta.", body_style)],
        [Paragraph("<b>/mie_offerte</b>", cmd_style), Paragraph("Gestisci e modifica le tue offerte pubblicate.", body_style)],
        [Paragraph("<b>/edit_offerta</b>", cmd_style), Paragraph("Modifica rapida di una specifica offerta attiva.", body_style)],
        [Paragraph("<b>/evidenza</b>", cmd_style), Paragraph("Dettagli e costi dei pacchetti promozionali e VIP.", body_style)],
        [Paragraph("<b>/guida</b>", cmd_style), Paragraph("Apri le guide d'uso e scarica i PDF ufficiali.", body_style)],
        [Paragraph("<b>/registrati</b>", cmd_style), Paragraph("Gestione scheda profilo e dati personali.", body_style)],
        [Paragraph("<b>/offerte</b>", cmd_style), Paragraph("Consulta l'elenco delle ultime offerte di lavoro.", body_style)],
        [Paragraph("<b>/regole</b>", cmd_style), Paragraph("Regolamento ufficiale della community.", body_style)],
        [Paragraph("<b>/formato</b>", cmd_style), Paragraph("Formato consigliato per la stesura post.", body_style)],
        [Paragraph("<b>/stats</b>", cmd_style), Paragraph("Statistiche aggiornate del gruppo Horeca Torino.", body_style)],
        [Paragraph("<b>/start</b>", cmd_style), Paragraph("Riavvia il bot e mostra il menu principale.", body_style)]
    ]

    table = Table(cmd_data, colWidths=[110, 410])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8f5e9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2e7d32')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#c8e6c9')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8faf8')])
    ]))

    story.append(table)
    doc.build(story)
    print(f"✅ Creato PDF Datori: {filename}")

if __name__ == "__main__":
    desktop_dir = "/Users/marcogiuridio/Desktop/CHAT TELEGRAM"
    pdf_candidati = os.path.join(desktop_dir, "Guida_Candidati_Horeca_Torino.pdf")
    pdf_datori = os.path.join(desktop_dir, "Guida_Datori_Horeca_Torino.pdf")
    
    create_candidate_pdf(pdf_candidati)
    create_employer_pdf(pdf_datori)

    # Also save inside bot/webapp directory for web serving
    webapp_dir = "/Users/marcogiuridio/Desktop/CHAT TELEGRAM/bot/webapp"
    create_candidate_pdf(os.path.join(webapp_dir, "Guida_Candidati_Horeca_Torino.pdf"))
    create_employer_pdf(os.path.join(webapp_dir, "Guida_Datori_Horeca_Torino.pdf"))
