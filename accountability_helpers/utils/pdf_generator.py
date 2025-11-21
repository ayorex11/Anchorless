from io import BytesIO
from decimal import Decimal
from django.core.files.base import ContentFile
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from datetime import date


def generate_payment_plan_pdf(debt_plan):
    """
    Generate a comprehensive PDF payment plan
    Returns BytesIO object with PDF content
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Container for PDF elements
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Title
    title = Paragraph(f"Debt Freedom Plan: {debt_plan.name}", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.2*inch))
    
    # Plan Overview
    overview_data = [
        ['Strategy:', debt_plan.get_strategy_display()],
        ['Monthly Budget:', f"${debt_plan.monthly_payment_budget:,.2f}"],
        ['Projected Payoff:', debt_plan.projected_payoff_date.strftime('%B %d, %Y') if debt_plan.projected_payoff_date else 'N/A'],
        ['Total Interest:', f"${debt_plan.total_interest_saved:,.2f}" if debt_plan.total_interest_saved else 'N/A'],
        ['Plan Created:', debt_plan.created_at.strftime('%B %d, %Y')],
    ]
    
    overview_table = Table(overview_data, colWidths=[2*inch, 4*inch])
    overview_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    elements.append(overview_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Loans Summary
    from Loan.models import Loan
    loans = Loan.objects.filter(debt_plan=debt_plan).order_by('payoff_order')
    
    if loans.exists():
        elements.append(Paragraph("Your Loans (in payoff order)", heading_style))
        elements.append(Spacer(1, 0.1*inch))
        
        loan_data = [['Order', 'Loan Name', 'Balance', 'Interest Rate', 'Min Payment']]
        for loan in loans:
            loan_data.append([
                str(loan.payoff_order) if loan.payoff_order else '-',
                loan.name[:30],
                f"${loan.remaining_balance:,.2f}",
                f"{loan.interest_rate}%",
                f"${loan.minimum_payment:,.2f}"
            ])
        
        loan_table = Table(loan_data, colWidths=[0.6*inch, 2.5*inch, 1.2*inch, 1*inch, 1.2*inch])
        loan_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        elements.append(loan_table)
        elements.append(Spacer(1, 0.3*inch))
    
    # Payment Schedule (first 12 months)
    from PaymentSchedule.models import PaymentSchedule
    schedules = PaymentSchedule.objects.filter(debt_plan=debt_plan).order_by('month_number')[:12]
    
    if schedules.exists():
        elements.append(Paragraph("Payment Schedule (First 12 Months)", heading_style))
        elements.append(Spacer(1, 0.1*inch))
        
        schedule_data = [['Month', 'Total Payment', 'Principal', 'Interest', 'Focus Loan']]
        for schedule in schedules:
            schedule_data.append([
                str(schedule.month_number),
                f"${schedule.total_payment:,.2f}",
                f"${schedule.total_principal:,.2f}",
                f"${schedule.total_interest:,.2f}",
                schedule.focus_loan.name[:20] if schedule.focus_loan else '-'
            ])
        
        schedule_table = Table(schedule_data, colWidths=[0.6*inch, 1.2*inch, 1.2*inch, 1*inch, 2.5*inch])
        schedule_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ecc71')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        
        elements.append(schedule_table)
    
    # Footer
    elements.append(Spacer(1, 0.5*inch))
    footer_text = f"Generated on {date.today().strftime('%B %d, %Y')} | Stay committed to your debt freedom journey!"
    footer = Paragraph(footer_text, styles['Normal'])
    elements.append(footer)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


def save_payment_plan_pdf(debt_plan):
    """
    Generate and save PDF for a debt plan
    Deletes old PDF if exists
    """
    from accountability_helpers.models import PaymentPlanPDF
    
    # Delete old PDF if exists
    try:
        old_pdf = PaymentPlanPDF.objects.get(debt_plan=debt_plan)
        old_pdf.delete_file()
        old_pdf.delete()
    except PaymentPlanPDF.DoesNotExist:
        pass
    
    # Generate new PDF
    pdf_buffer = generate_payment_plan_pdf(debt_plan)
    
    # Save to database
    pdf_plan = PaymentPlanPDF.objects.create(
        debt_plan=debt_plan,
        user=debt_plan.user
    )
    
    filename = f"payment_plan_{debt_plan.id}_{date.today().strftime('%Y%m%d')}.pdf"
    pdf_plan.pdf_file.save(filename, ContentFile(pdf_buffer.getvalue()), save=True)
    pdf_plan.file_size = pdf_plan.pdf_file.size
    pdf_plan.save(update_fields=['file_size'])
    
    return pdf_plan