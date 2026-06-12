"""
PDF Report Generation Service.

Generates a professional PDF report with forecast parameters,
model comparison metrics, forecast table, and interpretation.
Uses ReportLab for PDF creation.
"""

import io
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import (
    HexColor, white, black, lightgrey, Color
)
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# Brand colors
PRIMARY = HexColor('#1B263B')
ACCENT = HexColor('#3B82F6')
SUCCESS = HexColor('#10B981')
LIGHT_BG = HexColor('#F8FAFC')
MEDIUM_GRAY = HexColor('#64748B')
LIGHT_GRAY = HexColor('#E2E8F0')
GOLD = HexColor('#F59E0B')


def generate_forecast_pdf(context: dict) -> bytes:
    """
    Generate a PDF report from forecasting results.

    Args:
        context: dict returned by forecast_service.generate_forecast()

    Returns:
        PDF as bytes.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2 * cm,
        title='Reporte de Pronóstico – Criminalidad Alajuela',
        author='Sistema de Pronóstico de Criminalidad',
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Custom paragraph styles ──────────────────────────────────────────
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=22,
        textColor=PRIMARY,
        spaceAfter=6,
        alignment=TA_LEFT,
    )

    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        textColor=MEDIUM_GRAY,
        spaceAfter=16,
    )

    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        textColor=PRIMARY,
        spaceBefore=16,
        spaceAfter=8,
        borderPad=0,
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=HexColor('#334155'),
        spaceAfter=6,
        leading=14,
    )

    highlight_style = ParagraphStyle(
        'Highlight',
        parent=body_style,
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=PRIMARY,
        backColor=LIGHT_BG,
        borderPad=8,
        spaceAfter=12,
        leading=16,
    )

    # ── Header ──────────────────────────────────────────────────────────
    story.append(Paragraph('Criminalidad Alajuela', title_style))
    story.append(Paragraph('Reporte de Pronóstico de Criminalidad', subtitle_style))
    story.append(HRFlowable(width='100%', thickness=2, color=PRIMARY))
    story.append(Spacer(1, 12))

    # Generation date
    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    story.append(Paragraph(
        f'<font color="#64748B" size="9">Generado el {now} | Sistema de Pronóstico de Criminalidad – UCR Sede de Occidente</font>',
        ParagraphStyle('Meta', parent=body_style, alignment=TA_RIGHT, textColor=MEDIUM_GRAY)
    ))
    story.append(Spacer(1, 20))

    # ── Parameters Section ───────────────────────────────────────────────
    story.append(Paragraph('Parámetros del Análisis', h2_style))

    canton = context.get('canton', '-')
    delito = context.get('delito', '-')
    n_months = context.get('n_months', '-')
    best_method = context.get('best_method', '-')
    best_mae = context.get('best_mae', '-')
    best_accuracy = context.get('best_accuracy', '-')

    params_data = [
        ['Parámetro', 'Valor'],
        ['Cantón', canton.title()],
        ['Tipo de Delito', delito.title()],
        ['Meses pronosticados', str(n_months)],
        ['Mejor método', best_method],
        ['DMA (MAE) del mejor método', f'{best_mae:.4f}' if isinstance(best_mae, float) else str(best_mae)],
        ['Precisión del mejor método', f'{best_accuracy:.1f}%' if isinstance(best_accuracy, float) else str(best_accuracy)],
    ]

    param_table = Table(params_data, colWidths=[7 * cm, 9 * cm])
    param_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, LIGHT_BG]),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(param_table)
    story.append(Spacer(1, 16))

    # ── Composition (only for "Todos los delitos" queries) ───────────────
    composition_data = context.get('composition_data', [])
    if composition_data:
        story.append(Paragraph('Composición Histórica de Delitos', h2_style))
        comp_header = ['Tipo de Delito', 'Total registros', 'Porcentaje']
        comp_rows = [comp_header]
        for item in composition_data:
            comp_rows.append([
                item.get('delito', ''),
                str(item.get('total', '')),
                f"{item.get('pct', 0):.1f}%",
            ])
        comp_table = Table(comp_rows, colWidths=[7 * cm, 5 * cm, 5 * cm])
        comp_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, LIGHT_BG]),
            ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(comp_table)
        story.append(Spacer(1, 16))

    # ── Metrics Comparison ───────────────────────────────────────────────
    metrics = context.get('metrics_comparison', [])
    if metrics:
        story.append(Paragraph('Comparación de Métodos', h2_style))

        metrics_header = ['Método', 'DMA (MAE)', 'MSE', 'RMSE', 'Precisión', 'Estado']
        metrics_rows = [metrics_header]
        for m in metrics:
            status = '★ Mejor' if m.get('is_best') else ''
            metrics_rows.append([
                m.get('method', ''),
                f"{m.get('mae', 0):.4f}",
                f"{m.get('mse', 0):.4f}",
                f"{m.get('rmse', 0):.4f}",
                f"{m.get('accuracy', 0):.1f}%",
                status,
            ])

        col_widths = [5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2 * cm]
        metrics_table = Table(metrics_rows, colWidths=col_widths)
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, LIGHT_BG]),
            ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]

        # Highlight best row
        for i, m in enumerate(metrics, start=1):
            if m.get('is_best'):
                table_style.append(('BACKGROUND', (0, i), (-1, i), HexColor('#DBEAFE')))
                table_style.append(('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'))
                table_style.append(('TEXTCOLOR', (5, i), (5, i), ACCENT))

        metrics_table.setStyle(TableStyle(table_style))
        story.append(metrics_table)
        story.append(Spacer(1, 16))

    # ── Forecast Table ───────────────────────────────────────────────────
    forecast_table_data = context.get('forecast_table', [])
    if forecast_table_data:
        story.append(Paragraph(f'Pronóstico — {n_months} Meses', h2_style))

        ft_header = ['Período', 'Mes', 'Año', 'Pronóstico (delitos)']
        ft_rows = [ft_header]
        for row in forecast_table_data:
            ft_rows.append([
                row.get('period', ''),
                row.get('month_name', ''),
                str(row.get('year', '')),
                str(row.get('value', '')),
            ])

        col_widths = [3.5 * cm, 5 * cm, 3 * cm, 5.5 * cm]
        ft_table = Table(ft_rows, colWidths=col_widths)
        ft_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, LIGHT_BG]),
            ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('FONTNAME', (3, 1), (3, -1), 'Helvetica-Bold'),
        ]))
        story.append(ft_table)
        story.append(Spacer(1, 16))

    # ── Interpretation ───────────────────────────────────────────────────
    interpretation = context.get('interpretation', '')
    if interpretation:
        story.append(Paragraph('Interpretación Automática', h2_style))
        # Strip HTML tags for PDF (basic)
        clean_interp = interpretation.replace('<strong>', '').replace('</strong>', '')
        story.append(Paragraph(clean_interp, body_style))
        story.append(Spacer(1, 16))

    # ── Footer ──────────────────────────────────────────────────────────
    story.append(HRFlowable(width='100%', thickness=1, color=LIGHT_GRAY))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'Criminalidad Alajuela — IF-7200 Métodos Cuantitativos para la Toma de Decisiones '
        '— Universidad de Costa Rica, Sede de Occidente',
        ParagraphStyle(
            'Footer', parent=body_style,
            fontSize=8, textColor=MEDIUM_GRAY, alignment=TA_CENTER
        )
    ))

    doc.build(story)
    return buffer.getvalue()
