"""
PDF Report Generation Service — Professional Executive Design.

Produces a multi-page PDF report including:
  - Cover page with canton/crime-type branding
  - Executive summary with KPI cards
  - Embedded matplotlib charts (historical series + forecast, model MAE comparison)
  - Model comparison table with visual highlighting
  - Data-driven conclusions derived from actual results

Supports two report modes:
  - Standard: single crime type, four models compared, best selected by MAE.
  - Bottom-Up (is_aggregated_forecast=True): all crime types modelled individually
    then aggregated; shows per-type breakdown instead of model comparison.
"""

import io
import logging
from datetime import datetime

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak,
)
from reportlab.lib.enums import TA_CENTER

logger = logging.getLogger(__name__)

# ── Page geometry ─────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4                 # 595 × 842 pt
MARGIN_L = 2.2 * cm
MARGIN_R = 2.2 * cm
MARGIN_T = 3.0 * cm                 # space reserved for running header
MARGIN_B = 2.0 * cm                 # space reserved for footer
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R   # ≈ 16.6 cm

# ── Brand palette ─────────────────────────────────────────────────────────────
C_NAVY   = HexColor('#1B263B')
C_BLUE   = HexColor('#2563EB')
C_ORANGE = HexColor('#F97316')
C_GREEN  = HexColor('#10B981')
C_BG     = HexColor('#F8FAFC')
C_GRAY   = HexColor('#64748B')
C_BORDER = HexColor('#E2E8F0')
C_TEXT   = HexColor('#111827')
C_MUTED  = HexColor('#94A3B8')
C_COVER  = HexColor('#0F172A')      # darker navy for cover background

_MONTH_ES = {
    1:'Enero', 2:'Febrero', 3:'Marzo', 4:'Abril',
    5:'Mayo', 6:'Junio', 7:'Julio', 8:'Agosto',
    9:'Setiembre', 10:'Octubre', 11:'Noviembre', 12:'Diciembre',
}
_MONTH_SHORT = {
    1:'Ene', 2:'Feb', 3:'Mar', 4:'Abr', 5:'May', 6:'Jun',
    7:'Jul', 8:'Ago', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dic',
}


# ── Bottom-Up context normalisation ──────────────────────────────────────────
def _normalize_bottom_up_for_pdf(ctx: dict) -> dict:
    """
    The Bottom-Up result dict omits keys that the standard PDF sections expect
    (best_method, best_mae, best_accuracy, best_forecast, best_fitted, series …).
    This function adds them with semantically correct substitutes so all sections
    can render without crashing.  A shallow copy is returned; the original is
    not mutated.
    """
    out = dict(ctx)

    # Reconstruct 'series' list (dicts with year/month) from historical_labels
    if 'series' not in out:
        hist_labels = out.get('historical_labels', [])
        hist_values = out.get('historical_values', [])
        out['series'] = [
            {
                'year':  int(lbl[:4]),
                'month': int(lbl[5:7]),
                'total_delitos': val,
                'label': lbl,
            }
            for lbl, val in zip(hist_labels, hist_values)
        ]

    # Synthetic model fields
    out.setdefault('best_method',     'Pronóstico Bottom-Up')
    out.setdefault('best_method_key', 'bottom_up')
    out.setdefault('best_mae',        None)         # N/A for Bottom-Up
    out.setdefault('best_accuracy',   None)         # N/A for Bottom-Up
    out.setdefault('best_forecast',   out.get('bottom_up_forecast', []))
    out.setdefault('best_forecast_raw', out.get('bottom_up_forecast', []))
    out.setdefault('best_fitted',     [])           # no single fitted line
    out.setdefault('metrics_comparison', [])        # no per-model comparison
    out.setdefault('best_seasonal_list', [])

    return out


# ── Paragraph style factory ───────────────────────────────────────────────────
def _styles() -> dict:
    base = getSampleStyleSheet()

    def ps(name, **kw):
        return ParagraphStyle(name, parent=base['Normal'], **kw)

    return {
        'h1': ps('rpH1', fontName='Helvetica-Bold', fontSize=15, textColor=C_NAVY,
                  spaceBefore=0, spaceAfter=8, leading=20),
        'h2': ps('rpH2', fontName='Helvetica-Bold', fontSize=11, textColor=C_NAVY,
                  spaceBefore=14, spaceAfter=6, leading=15),
        'h2_orange': ps('rpH2O', fontName='Helvetica-Bold', fontSize=11, textColor=C_ORANGE,
                         spaceBefore=14, spaceAfter=6, leading=15),
        'body': ps('rpBody', fontName='Helvetica', fontSize=9.5, textColor=C_TEXT,
                    leading=14, spaceAfter=5),
        'body_sm': ps('rpSm', fontName='Helvetica', fontSize=8.5, textColor=C_GRAY,
                       leading=12, spaceAfter=4),
        'caption': ps('rpCap', fontName='Helvetica-Oblique', fontSize=8, textColor=C_GRAY,
                       spaceAfter=10, alignment=TA_CENTER),
        'kpi_val': ps('rpKPI', fontName='Helvetica-Bold', fontSize=20, textColor=C_NAVY,
                       alignment=TA_CENTER, leading=26),
        'kpi_lbl': ps('rpKL', fontName='Helvetica', fontSize=7.5, textColor=C_GRAY,
                       alignment=TA_CENTER, leading=10),
        'note': ps('rpNote', fontName='Helvetica-Oblique', fontSize=8.5, textColor=C_GRAY,
                    leading=12, spaceAfter=6),
    }


# ── Matplotlib charts ─────────────────────────────────────────────────────────
def _fig_to_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=130, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _apply_ax_style(ax):
    ax.set_facecolor('#F8FAFC')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#E2E8F0')
    ax.spines['bottom'].set_color('#E2E8F0')
    ax.tick_params(colors='#64748B', labelsize=8)
    ax.grid(True, axis='y', color='#E2E8F0', linewidth=0.7, alpha=0.9)


def _chart_series_forecast(ctx: dict):
    """
    Line chart: full historical series + model fit + forecast.
    Returns PNG bytes or None if matplotlib is unavailable or data is missing.
    For Bottom-Up mode the fitted line is omitted (best_fitted is empty).
    """
    if not _HAS_MPL:
        return None

    hist_labels  = ctx.get('historical_labels', [])
    hist_values  = ctx.get('historical_values', [])
    fore_labels  = ctx.get('forecast_labels', [])
    fore_values  = ctx.get('best_forecast_raw', ctx.get('best_forecast', []))
    fitted       = ctx.get('best_fitted', [])

    if not hist_values or not fore_values:
        return None

    n = len(hist_values)

    fig, ax = plt.subplots(figsize=(12, 3.9), facecolor='white')
    _apply_ax_style(ax)

    # Historical area + line
    ax.fill_between(range(n), hist_values, alpha=0.09, color='#1B263B')
    ax.plot(range(n), hist_values, color='#1B263B', linewidth=1.6,
            label='Serie histórica', zorder=3)

    # Model fit (dashed) — skipped for Bottom-Up (fitted=[])
    if fitted and len(fitted) == n:
        ax.plot(range(n), fitted, color='#2563EB', linewidth=0.85,
                linestyle='--', alpha=0.65, label='Ajuste del modelo', zorder=2)

    # Forecast (connects smoothly from last historical point)
    x_fore = list(range(n - 1, n + len(fore_values)))
    y_fore = [hist_values[-1]] + list(fore_values)
    ax.fill_between(x_fore, y_fore, alpha=0.12, color='#F97316')

    forecast_label = ('Pronóstico Bottom-Up' if ctx.get('is_aggregated_forecast')
                      else 'Pronóstico')
    ax.plot(x_fore, y_fore, color='#F97316', linewidth=2.0,
            label=forecast_label, marker='o', markersize=3.5, zorder=4)

    # Vertical divider between historical and forecast
    ax.axvline(x=n - 1, color='#CBD5E1', linestyle='--', linewidth=0.8)
    y_top = ax.get_ylim()[1]
    ax.text(n - 0.5, y_top * 0.95, 'pronóstico →', fontsize=7,
            color='#94A3B8', va='top', ha='left')

    # X-axis: show only year boundaries to avoid label crowding
    all_labels = hist_labels + fore_labels
    xt, xl = [], []
    for i, lbl in enumerate(all_labels):
        try:
            mo = int(lbl[5:7])
        except (ValueError, IndexError):
            continue
        if mo == 1 or (len(all_labels) < 20 and mo == 7):
            xt.append(i)
            xl.append(lbl[:4] if mo == 1 else _MONTH_SHORT.get(mo, '') + ' ' + lbl[:4])
    ax.set_xticks(xt)
    ax.set_xticklabels(xl, fontsize=8, rotation=0)

    ax.set_ylabel('Delitos registrados', fontsize=8.5, color='#334155')
    ax.legend(fontsize=7.5, framealpha=0.95, loc='upper left',
              frameon=True, edgecolor='#E2E8F0')
    ax.set_xlim(-0.5, n + len(fore_values) - 0.5)

    plt.tight_layout(pad=0.5)
    return _fig_to_bytes(fig)


def _chart_mae_comparison(metrics: list):
    """
    Horizontal bar chart comparing MAE across all models.
    Best model highlighted in orange; others in light blue-gray.
    Returns None if metrics is empty (e.g. Bottom-Up mode).
    """
    if not _HAS_MPL or not metrics:
        return None

    names  = [m['method'] for m in metrics]
    maes   = [m['mae'] for m in metrics]
    colors = ['#F97316' if m['is_best'] else '#CBD5E1' for m in metrics]

    fig, ax = plt.subplots(figsize=(10, 2.4), facecolor='white')
    _apply_ax_style(ax)
    ax.grid(True, axis='x', color='#E2E8F0', linewidth=0.7)
    ax.grid(False, axis='y')

    bars = ax.barh(names, maes, color=colors, height=0.45, zorder=3)

    max_mae = max(maes) if maes else 1
    for bar, mae, m in zip(bars, maes, metrics):
        label = f'  {mae:.3f}' + (' ← mejor' if m['is_best'] else '')
        color = '#F97316' if m['is_best'] else '#64748B'
        ax.text(bar.get_width() + max_mae * 0.01, bar.get_y() + bar.get_height() / 2,
                label, va='center', fontsize=8.5, color=color,
                fontweight='bold' if m['is_best'] else 'normal')

    ax.set_xlabel('DMA — Error Absoluto Medio (menor es mejor)', fontsize=8.5, color='#334155')
    ax.set_xlim(0, max_mae * 1.30)
    ax.invert_yaxis()

    plt.tight_layout(pad=0.4)
    return _fig_to_bytes(fig)


def _make_image(png_bytes: bytes, width: float, height: float):
    """Wrap PNG bytes in a ReportLab Image flowable."""
    from reportlab.platypus import Image as RLImage
    buf = io.BytesIO(png_bytes)
    return RLImage(buf, width=width, height=height)


# ── Canvas callbacks ──────────────────────────────────────────────────────────
def _draw_cover(canvas, _doc, ctx: dict):
    """
    Render a clean, minimal cover page on white background.
    Called as the onFirstPage callback — no flowables render here.
    """
    canvas.saveState()
    w, h = PAGE_W, PAGE_H

    is_agg = ctx.get('is_aggregated_forecast', False)

    # ── Top navy header bar ───────────────────────────────────────────────────
    BAR_H = 2.8 * cm
    canvas.setFillColor(C_NAVY)
    canvas.rect(0, h - BAR_H, w, BAR_H, fill=1, stroke=0)

    # Orange left accent inside the bar
    canvas.setFillColor(C_ORANGE)
    canvas.rect(0, h - BAR_H, 4 * mm, BAR_H, fill=1, stroke=0)

    # System name (white in bar)
    canvas.setFillColor(white)
    canvas.setFont('Helvetica-Bold', 15)
    canvas.drawString(1.2 * cm, h - 1.55 * cm, 'Sistema de Pronóstico de Criminalidad')
    canvas.setFillColor(C_MUTED)
    canvas.setFont('Helvetica', 9)
    canvas.drawString(1.2 * cm, h - 2.2 * cm, 'Alajuela · Costa Rica')

    # ── Report label ──────────────────────────────────────────────────────────
    canvas.setFillColor(C_MUTED)
    canvas.setFont('Helvetica', 8)
    canvas.drawString(2.0 * cm, h - 4.2 * cm, 'REPORTE DE PRONÓSTICO')

    # ── Canton name (large) ───────────────────────────────────────────────────
    canton   = ctx.get('canton', '').title()
    delito   = ctx.get('delito', '').title()
    n_months = ctx.get('n_months', '')

    canvas.setFillColor(C_NAVY)
    canvas.setFont('Helvetica-Bold', 26)
    canvas.drawString(2.0 * cm, h - 5.6 * cm, canton)

    # Orange underline below canton name
    name_w = canvas.stringWidth(canton, 'Helvetica-Bold', 26)
    canvas.setStrokeColor(C_ORANGE)
    canvas.setLineWidth(2)
    canvas.line(2.0 * cm, h - 5.9 * cm, 2.0 * cm + name_w, h - 5.9 * cm)

    # ── Delito ────────────────────────────────────────────────────────────────
    canvas.setFillColor(C_GRAY)
    canvas.setFont('Helvetica', 14)
    canvas.drawString(2.0 * cm, h - 7.1 * cm, delito)

    # ── Info grid ────────────────────────────────────────────────────────────
    hist_values  = ctx.get('historical_values', [])
    series       = ctx.get('series', [])
    n_periods    = len(hist_values)
    total_events = sum(hist_values)

    # Period string derived from series list or historical_labels
    period_str = '—'
    if series:
        s0, s1 = series[0], series[-1]
        period_str = f"{s0['year']}–{s1['year']}"
    else:
        lbls = ctx.get('historical_labels', [])
        if lbls:
            period_str = f"{lbls[0][:4]}–{lbls[-1][:4]}"

    cards = [
        ('Período',   period_str),
        ('Meses',     str(n_periods)),
        ('Eventos',   f'{total_events:,}'),
        ('Horizonte', f'{n_months} m.'),
    ]

    grid_y  = h - 11.5 * cm
    grid_x  = 2.0 * cm
    cell_w  = (w - 4.0 * cm) / 4
    cell_h  = 2.0 * cm
    pad     = 4 * mm

    for i, (lbl, val) in enumerate(cards):
        x = grid_x + i * cell_w
        canvas.setStrokeColor(C_BORDER)
        canvas.setFillColor(C_BG)
        canvas.setLineWidth(0.5)
        canvas.rect(x, grid_y, cell_w - 3 * mm, cell_h, fill=1, stroke=1)
        canvas.setFillColor(C_NAVY)
        canvas.setFont('Helvetica-Bold', 14)
        canvas.drawString(x + pad, grid_y + cell_h - 0.85 * cm, val)
        canvas.setFillColor(C_GRAY)
        canvas.setFont('Helvetica', 8)
        canvas.drawString(x + pad, grid_y + pad, lbl)

    # ── Model info row ────────────────────────────────────────────────────────
    model_y = grid_y - 1.6 * cm
    canvas.setStrokeColor(C_BORDER)
    canvas.setFillColor(white)
    canvas.setLineWidth(0.5)
    canvas.rect(2.0 * cm, model_y, w - 4.0 * cm, 1.2 * cm, fill=1, stroke=1)
    # Orange left accent
    canvas.setFillColor(C_ORANGE)
    canvas.rect(2.0 * cm, model_y, 3 * mm, 1.2 * cm, fill=1, stroke=0)

    if is_agg:
        label_top  = 'METODOLOGÍA'
        n_types    = ctx.get('n_crime_types', '?')
        label_main = f'Pronóstico Bottom-Up   ·   {n_types} tipos de delito modelados individualmente'
    else:
        best_method   = ctx.get('best_method', '—')
        best_accuracy = ctx.get('best_accuracy', 0) or 0
        label_top  = 'MODELO RECOMENDADO'
        label_main = f'{best_method}   ·   Precisión: {best_accuracy:.1f}%'

    canvas.setFillColor(C_GRAY)
    canvas.setFont('Helvetica', 7.5)
    canvas.drawString(2.0 * cm + 6 * mm, model_y + 0.82 * cm, label_top)
    canvas.setFillColor(C_NAVY)
    canvas.setFont('Helvetica-Bold', 9.5)
    canvas.drawString(2.0 * cm + 6 * mm, model_y + 0.25 * cm, label_main)

    # ── Bottom divider + institution ──────────────────────────────────────────
    canvas.setStrokeColor(C_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(2.0 * cm, 2.8 * cm, w - 2.0 * cm, 2.8 * cm)

    canvas.setFillColor(C_GRAY)
    canvas.setFont('Helvetica', 8)
    canvas.drawCentredString(w / 2, 2.0 * cm,
                             'Universidad de Costa Rica · Sede de Occidente · IF-7200')
    canvas.setFillColor(C_MUTED)
    canvas.setFont('Helvetica', 8)
    now_str = datetime.now().strftime('%d de %B de %Y')
    canvas.drawCentredString(w / 2, 1.3 * cm, now_str)

    canvas.restoreState()


def _draw_content_page(canvas, _doc, ctx: dict):
    """
    Draw running header and footer on every content page (pages 2+).
    """
    canvas.saveState()
    w = PAGE_W

    canton = ctx.get('canton', '').title()
    delito = ctx.get('delito', '').title()

    # ── Header ────────────────────────────────────────────────────────────────
    header_y = PAGE_H - 1.5 * cm
    canvas.setStrokeColor(C_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN_L, header_y - 0.1 * cm, w - MARGIN_R, header_y - 0.1 * cm)

    canvas.setFillColor(C_NAVY)
    canvas.setFont('Helvetica-Bold', 8)
    canvas.drawString(MARGIN_L, header_y, 'Pronóstico de Criminalidad · Alajuela')

    canvas.setFillColor(C_GRAY)
    canvas.setFont('Helvetica', 8)
    label = f'{canton} / {delito}'
    canvas.drawRightString(w - MARGIN_R, header_y, label)

    # Orange accent line under header
    canvas.setStrokeColor(C_ORANGE)
    canvas.setLineWidth(1.5)
    canvas.line(MARGIN_L, header_y - 0.35 * cm, MARGIN_L + 2.5 * cm, header_y - 0.35 * cm)

    # ── Footer ────────────────────────────────────────────────────────────────
    footer_y = MARGIN_B - 0.5 * cm
    canvas.setStrokeColor(C_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN_L, footer_y + 0.35 * cm, w - MARGIN_R, footer_y + 0.35 * cm)

    now_str = datetime.now().strftime('%d/%m/%Y')
    canvas.setFillColor(C_MUTED)
    canvas.setFont('Helvetica', 7.5)
    canvas.drawString(MARGIN_L, footer_y, now_str)

    canvas.drawCentredString(w / 2, footer_y,
                             'IF-7200 Métodos Cuantitativos · UCR Sede de Occidente')

    canvas.setFont('Helvetica-Bold', 7.5)
    canvas.drawRightString(w - MARGIN_R, footer_y, f'Página {canvas._pageNumber - 1}')

    canvas.restoreState()


# ── Section builders ──────────────────────────────────────────────────────────
def _section_heading(text: str, S: dict, accent_color=None) -> list:
    """Return [bar, heading] — include in a KeepTogether at the call site."""
    color = accent_color or C_NAVY
    bar = HRFlowable(width='100%', thickness=3, color=color, spaceBefore=14, spaceAfter=4)
    return [bar, Paragraph(text, S['h2'])]


def _section_executive_summary(ctx: dict, S: dict) -> list:
    """
    4 KPI cards + a concise text block summarising the key findings.
    No filler text — every sentence derives from the actual data.
    """
    elems = _section_heading('Resumen ejecutivo', S, C_ORANGE)

    is_agg       = ctx.get('is_aggregated_forecast', False)
    hist_values  = ctx.get('historical_values', [])
    fore_values  = ctx.get('bottom_up_forecast', []) if is_agg else ctx.get('best_forecast', [])
    best_method  = ctx.get('best_method', '—')
    best_mae     = ctx.get('best_mae')     # None for Bottom-Up
    best_acc     = ctx.get('best_accuracy')  # None for Bottom-Up
    series       = ctx.get('series', [])

    # Derived statistics
    n_periods    = len(hist_values)
    total_events = sum(hist_values)
    recent_avg   = (sum(hist_values[-6:]) / 6) if len(hist_values) >= 6 else (
                    sum(hist_values) / len(hist_values) if hist_values else 0)
    fore_avg     = sum(fore_values) / len(fore_values) if fore_values else 0
    pct_change   = ((fore_avg - recent_avg) / recent_avg * 100) if recent_avg > 0 else 0

    # Period string
    period_str = '—'
    if series:
        s0, s1 = series[0], series[-1]
        period_str = (f"{_MONTH_ES.get(s0['month'], '')} {s0['year']} – "
                      f"{_MONTH_ES.get(s1['month'], '')} {s1['year']}")
    else:
        lbls = ctx.get('historical_labels', [])
        if lbls:
            period_str = f"{lbls[0][:4]} – {lbls[-1][:4]}"

    # KPI grid
    period_kpi = '—'
    if series:
        s0, s1 = series[0], series[-1]
        period_kpi = f"{s0['year']}–{s1['year']}"
    else:
        lbls = ctx.get('historical_labels', [])
        if lbls:
            period_kpi = f"{lbls[0][:4]}–{lbls[-1][:4]}"

    kpi_val_style = [
        ('ALIGN',        (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 8),
        ('LEFTPADDING',  (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND',   (0, 0), (-1, -1), C_BG),
        ('GRID',         (0, 0), (-1, -1), 0.5, C_BORDER),
        ('LINEABOVE',    (0, 0), (0, 0), 3, C_ORANGE),
        ('LINEABOVE',    (1, 0), (1, 0), 3, C_NAVY),
        ('LINEABOVE',    (2, 0), (2, 0), 3, C_BLUE),
        ('LINEABOVE',    (3, 0), (3, 0), 3, C_GREEN),
    ]

    kpi_val_sm = ParagraphStyle(
        'rpKPIsm', parent=S['kpi_val'], fontSize=16, leading=20,
    )

    def _kpi(val_str, lbl_str):
        col_w = CONTENT_W / 4 - 3 * mm
        return Table(
            [[Paragraph(val_str, kpi_val_sm)],
             [Paragraph(lbl_str, S['kpi_lbl'])]],
            colWidths=[col_w],
        )

    trend_icon = '↑' if pct_change > 5 else ('↓' if pct_change < -5 else '→')
    cards_data = [[
        _kpi(period_kpi,                       'Período'),
        _kpi(f'{n_periods} meses',             'Datos históricos'),
        _kpi(f'{total_events:,}',              'Eventos registrados'),
        _kpi(f'{trend_icon} {abs(pct_change):.1f}%', 'Variación proyectada'),
    ]]
    cards_table = Table(cards_data, colWidths=[CONTENT_W / 4] * 4)
    cards_table.setStyle(TableStyle(kpi_val_style))
    elems.append(cards_table)
    elems.append(Spacer(1, 10))

    # Narrative
    canton   = ctx.get('canton', '').title()
    delito   = ctx.get('delito', '').title()
    n_months = ctx.get('n_months', '—')

    peak_idx   = hist_values.index(max(hist_values)) if hist_values else 0
    peak_label = ctx.get('historical_labels', ['—'])[peak_idx] if hist_values else '—'

    direction_word = ('un incremento' if pct_change > 5 else
                      'una reducción' if pct_change < -5 else 'un comportamiento estable')

    if is_agg:
        n_types = ctx.get('n_crime_types', '?')
        summary_text = (
            f"El análisis cubre <b>{n_periods} meses</b> de registros históricos "
            f"en el cantón de {canton} ({period_str}), con un total de "
            f"<b>{total_events:,} eventos registrados</b>. "
            f"Se aplicó el método <b>Bottom-Up</b>: {n_types} tipos de delito fueron "
            f"modelados individualmente con el modelo más adecuado según su frecuencia "
            f"histórica, y los pronósticos se sumaron para obtener el total del cantón. "
            f"Para el horizonte de {n_months} meses, el sistema proyecta {direction_word} "
            f"del <b>{abs(pct_change):.1f}%</b> respecto al promedio reciente "
            f"({recent_avg:.1f} eventos/mes). "
            f"El período de mayor incidencia registrado fue {peak_label} "
            f"con {max(hist_values) if hist_values else 0:,} eventos."
        )
    else:
        mae_str = f"{best_mae:.2f}" if best_mae is not None else "N/D"
        acc_str = f"{best_acc:.1f}%" if best_acc is not None else "N/D"
        summary_text = (
            f"El análisis cubre <b>{n_periods} meses</b> de registros de <i>{delito.lower()}</i> "
            f"en el cantón de {canton} ({period_str}), con un total de "
            f"<b>{total_events:,} eventos registrados</b>. "
            f"El modelo de mejor desempeño fue <b>{best_method}</b>, "
            f"con una DMA de {mae_str} y una precisión del {acc_str}. "
            f"Para el horizonte de pronóstico de {n_months} meses, "
            f"el modelo proyecta {direction_word} "
            f"del <b>{abs(pct_change):.1f}%</b> respecto al promedio reciente "
            f"({recent_avg:.1f} eventos/mes). "
            f"El período de mayor incidencia registrado fue {peak_label} "
            f"con {max(hist_values) if hist_values else 0:,} eventos."
        )
    elems.append(Paragraph(summary_text, S['body']))
    return elems


def _section_parameters(ctx: dict, S: dict) -> list:
    """Compact parameters table."""
    is_agg   = ctx.get('is_aggregated_forecast', False)
    canton   = ctx.get('canton', '—').title()
    delito   = ctx.get('delito', '—').title()
    n_months = ctx.get('n_months', '—')
    series   = ctx.get('series', [])

    date_from = '—'
    date_to   = '—'
    if series:
        s0, s1 = series[0], series[-1]
        date_from = f"{_MONTH_ES.get(s0['month'], '')} {s0['year']}"
        date_to   = f"{_MONTH_ES.get(s1['month'], '')} {s1['year']}"
    else:
        lbls = ctx.get('historical_labels', [])
        if lbls:
            date_from = f"{_MONTH_ES.get(int(lbls[0][5:7]), '')} {lbls[0][:4]}"
            date_to   = f"{_MONTH_ES.get(int(lbls[-1][5:7]), '')} {lbls[-1][:4]}"

    def _cell(text, bold=False):
        style = ParagraphStyle(
            'pc', parent=S['body'],
            fontName='Helvetica-Bold' if bold else 'Helvetica',
            fontSize=9, leading=13,
        )
        return Paragraph(text, style)

    def _label(text):
        return Paragraph(text, ParagraphStyle(
            'pl', parent=S['body_sm'], fontName='Helvetica-Bold',
            fontSize=9, textColor=C_GRAY, leading=13,
        ))

    if is_agg:
        n_types     = ctx.get('n_crime_types', '?')
        method_lbl  = 'Metodología'
        method_val  = f'Bottom-Up ({n_types} tipos de delito)'
    else:
        method_lbl  = 'Modelo óptimo'
        method_val  = ctx.get('best_method', '—')

    rows = [
        [_label('Cantón'),         _cell(canton),
         _label('Horizonte'),      _cell(f'{n_months} meses')],
        [_label('Tipo de delito'), _cell(delito),
         _label('Inicio'),         _cell(date_from)],
        [_label(method_lbl),       _cell(method_val),
         _label('Fin'),            _cell(date_to)],
    ]

    col_w = [2.8 * cm, CONTENT_W / 2 - 2.8 * cm, 2.8 * cm, CONTENT_W / 2 - 2.8 * cm]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [white, C_BG]),
        ('GRID',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING',     (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 7),
        ('LEFTPADDING',    (0, 0), (-1, -1), 8),
        ('VALIGN',         (0, 0), (-1, -1), 'TOP'),
    ]))
    return [KeepTogether(_section_heading('Parámetros del análisis', S) + [t])]


def _section_historical_forecast(ctx: dict, S: dict, chart_bytes) -> list:
    """Chart + forecast table."""
    hist_values = ctx.get('historical_values', [])

    note_para = None
    if hist_values:
        avg_monthly = sum(hist_values) / len(hist_values)
        note_para = Paragraph(
            f"Promedio mensual histórico: <b>{avg_monthly:.1f}</b> eventos · "
            f"Máximo: <b>{max(hist_values)}</b> · Mínimo: <b>{min(hist_values)}</b>",
            S['body_sm'],
        )

    is_agg = ctx.get('is_aggregated_forecast', False)
    chart_title = ('Serie histórica total y pronóstico Bottom-Up'
                   if is_agg else 'Serie histórica y pronóstico')
    chart_block = _section_heading(chart_title, S)
    if note_para:
        chart_block.append(note_para)
    if chart_bytes:
        chart_h = CONTENT_W * (3.9 / 12)
        chart_block.append(_make_image(chart_bytes, CONTENT_W, chart_h))
        if is_agg:
            caption = (
                'La línea naranja representa el pronóstico Bottom-Up (suma de los '
                'pronósticos individuales por tipo de delito).'
            )
        else:
            caption = (
                'La línea naranja representa el pronóstico generado por el modelo seleccionado. '
                'La línea azul punteada muestra el ajuste del modelo al período histórico.'
            )
        chart_block.append(Paragraph(caption, S['caption']))
    else:
        chart_block.append(Paragraph('Gráfico no disponible (requiere matplotlib).', S['note']))

    elems = [KeepTogether(chart_block), Spacer(1, 6)]

    forecast_table = ctx.get('forecast_table', [])
    if forecast_table:
        best_raw = max((r.get('value_raw', r.get('value', 0)) for r in forecast_table), default=0)
        rows = [['Período', 'Mes', 'Año', 'Proyectado', 'Redondeado']]
        for row in forecast_table:
            raw_val = row.get('value_raw', row.get('value', ''))
            rows.append([
                row.get('period', ''),
                row.get('month_name', ''),
                str(row.get('year', '')),
                f"{raw_val:.2f}" if isinstance(raw_val, float) else str(raw_val),
                str(row.get('value', '')),
            ])

        col_w = [2.8 * cm, 4.8 * cm, 2.2 * cm, 3.5 * cm, 3.3 * cm]
        ft = Table(rows, colWidths=col_w, repeatRows=1)
        style = [
            ('BACKGROUND',     (0, 0), (-1, 0), C_NAVY),
            ('TEXTCOLOR',      (0, 0), (-1, 0), white),
            ('FONTNAME',       (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',       (0, 0), (-1, 0), 9),
            ('FONTNAME',       (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE',       (0, 1), (-1, -1), 9),
            ('ALIGN',          (0, 0), (-1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_BG]),
            ('GRID',           (0, 0), (-1, -1), 0.5, C_BORDER),
            ('TOPPADDING',     (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING',  (0, 0), (-1, -1), 7),
            # "Proyectado" column (index 3) — bold navy
            ('FONTNAME',       (3, 1), (3, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR',      (3, 1), (3, -1), C_NAVY),
            # "Redondeado" column (index 4) — muted
            ('TEXTCOLOR',      (4, 1), (4, -1), C_GRAY),
        ]
        for i, row in enumerate(forecast_table, start=1):
            raw_val = row.get('value_raw', row.get('value', 0))
            if isinstance(raw_val, (int, float)) and raw_val == best_raw:
                style += [
                    ('BACKGROUND', (3, i), (3, i), HexColor('#FFF7ED')),
                    ('TEXTCOLOR',  (3, i), (3, i), C_ORANGE),
                ]
        ft.setStyle(TableStyle(style))
        sub_heading = Paragraph('Detalle del pronóstico por período', S['h2'])
        elems.append(KeepTogether([sub_heading, ft]))

    return elems


def _section_metrics(ctx: dict, S: dict, chart_bytes) -> list:
    """Model comparison: bar chart + detailed metrics table. Skipped for Bottom-Up."""
    metrics = ctx.get('metrics_comparison', [])
    if not metrics:
        return []

    best_m  = next((m for m in metrics if m.get('is_best')), metrics[0])
    worst_m = metrics[-1]
    mae_gap = worst_m['mae'] - best_m['mae']

    intro = Paragraph(
        f"Se evaluaron {len(metrics)} modelos cuantitativos sobre el mismo período histórico. "
        f"<b>{best_m['method']}</b> obtuvo el menor error absoluto medio "
        f"(DMA = {best_m['mae']:.3f}), superando al siguiente modelo por "
        f"{mae_gap:.3f} unidades.",
        S['body'],
    )

    chart_img = None
    if chart_bytes:
        chart_h = CONTENT_W * (2.4 / 10)
        chart_img = _make_image(chart_bytes, CONTENT_W * 0.9, chart_h)

    hdr = ['Modelo', 'DMA (MAE)', 'MSE', 'RMSE', 'Precisión', '']
    rows = [hdr]
    for m in metrics:
        rows.append([
            m.get('method', ''),
            f"{m.get('mae', 0):.4f}",
            f"{m.get('mse', 0):.4f}",
            f"{m.get('rmse', 0):.4f}",
            f"{m.get('accuracy', 0):.1f}%",
            'Seleccionado' if m.get('is_best') else '',
        ])

    col_w = [5.0 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.3 * cm, 2.3 * cm]
    t = Table(rows, colWidths=col_w)
    style = [
        ('BACKGROUND',     (0, 0), (-1, 0), C_NAVY),
        ('TEXTCOLOR',      (0, 0), (-1, 0), white),
        ('FONTNAME',       (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',       (0, 0), (-1, 0), 8.5),
        ('FONTNAME',       (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',       (0, 1), (-1, -1), 8.5),
        ('ALIGN',          (0, 0), (0, -1), 'LEFT'),
        ('ALIGN',          (1, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_BG]),
        ('GRID',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING',     (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 7),
        ('LEFTPADDING',    (0, 0), (0, -1), 8),
    ]
    for i, m in enumerate(metrics, start=1):
        if m.get('is_best'):
            style += [
                ('BACKGROUND', (0, i), (-1, i), HexColor('#FFF7ED')),
                ('FONTNAME',   (0, i), (-1, i), 'Helvetica-Bold'),
                ('TEXTCOLOR',  (5, i), (5, i),  C_ORANGE),
            ]
    t.setStyle(TableStyle(style))

    block = _section_heading('Evaluación y comparación de modelos', S) + [intro]
    if chart_img:
        block += [chart_img, Spacer(1, 4)]
    block.append(t)
    return [KeepTogether(block)]


def _section_breakdown(ctx: dict, S: dict) -> list:
    """Per-crime-type breakdown table — only included for Bottom-Up reports."""
    breakdown = ctx.get('breakdown', [])
    if not breakdown:
        return []

    freq_labels = {'alta': 'Alta', 'media': 'Media', 'baja': 'Baja'}

    intro = Paragraph(
        f"Desglose de los {len(breakdown)} tipos de delito modelados individualmente, "
        f"ordenados por contribución al pronóstico total (mayor → menor).",
        S['body_sm'],
    )

    hdr = ['Tipo de delito', 'Modelo aplicado', 'Clase', 'DMA', 'Pron. prom./mes', 'Contribución']
    rows = [hdr]
    for item in breakdown:
        rows.append([
            item.get('crime_type', ''),
            item.get('model_used', ''),
            freq_labels.get(item.get('frequency_class', ''), '—'),
            f"{item.get('dma', 0):.4f}",
            f"{item.get('forecast_avg', 0):.2f}",
            f"{item.get('contribution_pct', 0):.1f}%",
        ])

    col_w = [3.8 * cm, 4.0 * cm, 1.5 * cm, 2.0 * cm, 2.5 * cm, 2.7 * cm]
    t = Table(rows, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, 0), C_NAVY),
        ('TEXTCOLOR',      (0, 0), (-1, 0), white),
        ('FONTNAME',       (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',       (0, 0), (-1, 0), 8.5),
        ('FONTNAME',       (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',       (0, 1), (-1, -1), 8.5),
        ('ALIGN',          (0, 0), (0, -1), 'LEFT'),
        ('ALIGN',          (1, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_BG]),
        ('GRID',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING',     (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 6),
        ('LEFTPADDING',    (0, 0), (0, -1), 6),
    ]))

    elems = _section_heading('Desglose Bottom-Up por tipo de delito', S) + [intro, t]

    warnings = ctx.get('warnings', [])
    if warnings:
        elems.append(Spacer(1, 6))
        elems.append(Paragraph(
            'Notas del modelado:',
            ParagraphStyle('nhead', parent=S['body_sm'],
                           fontName='Helvetica-Bold', fontSize=8.5),
        ))
        for w in warnings[:10]:
            elems.append(Paragraph(f'• {w}', S['note']))

    return [KeepTogether(elems)]


def _section_composition(ctx: dict, S: dict) -> list:
    """Crime type breakdown — only included for 'all crimes' queries."""
    comp = ctx.get('composition_data', [])
    if not comp:
        return []

    intro = Paragraph(
        f"Distribución de los {len(comp)} tipos de delito registrados "
        f"en el período analizado (ordenados por frecuencia).",
        S['body_sm'],
    )

    rows = [['Tipo de delito', 'Total', '%']]
    for item in comp[:15]:
        rows.append([
            item.get('delito', ''),
            f"{item.get('total', 0):,}",
            f"{item.get('pct', 0):.1f}%",
        ])

    col_w = [9.0 * cm, 4.0 * cm, 3.6 * cm]
    t = Table(rows, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, 0), C_NAVY),
        ('TEXTCOLOR',      (0, 0), (-1, 0), white),
        ('FONTNAME',       (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',       (0, 0), (-1, 0), 9),
        ('FONTNAME',       (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',       (0, 1), (-1, -1), 9),
        ('ALIGN',          (1, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_BG]),
        ('GRID',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING',     (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 6),
        ('LEFTPADDING',    (0, 0), (0, -1), 8),
    ]))
    return [KeepTogether(_section_heading('Composición por tipo de delito', S) + [intro, t])]


def _section_conclusions(ctx: dict, S: dict) -> list:
    """
    Data-driven conclusions: trend, methodology rationale, forecast summary, quality.
    Adapts automatically for Bottom-Up vs. standard single-model reports.
    """
    elems = _section_heading('Conclusiones y hallazgos', S)

    is_agg        = ctx.get('is_aggregated_forecast', False)
    hist_values   = ctx.get('historical_values', [])
    fore_values   = (ctx.get('bottom_up_forecast', []) if is_agg
                     else ctx.get('best_forecast', []))
    best_method   = ctx.get('best_method', '—')
    best_key      = ctx.get('best_method_key', '')
    best_mae      = ctx.get('best_mae')
    best_acc      = ctx.get('best_accuracy')
    canton        = ctx.get('canton', '').title()
    delito        = ctx.get('delito', '').title()
    n_months      = ctx.get('n_months', '—')
    interpretation = ctx.get('interpretation', '')

    if not hist_values:
        elems.append(Paragraph('Sin datos históricos suficientes para generar conclusiones.', S['body']))
        return elems

    n = len(hist_values)
    recent_avg = sum(hist_values[-6:]) / 6 if n >= 6 else sum(hist_values) / n
    fore_avg   = sum(fore_values) / len(fore_values) if fore_values else 0
    pct_change = (fore_avg - recent_avg) / recent_avg * 100 if recent_avg > 0 else 0

    # ── 1. Historical trend ───────────────────────────────────────────────────
    first_q = hist_values[:max(1, n // 4)]
    last_q  = hist_values[-max(1, n // 4):]
    avg_first = sum(first_q) / len(first_q)
    avg_last  = sum(last_q) / len(last_q)
    long_pct  = (avg_last - avg_first) / avg_first * 100 if avg_first > 0 else 0

    if long_pct > 10:
        trend_text = (f"La serie histórica muestra una <b>tendencia creciente</b> de largo plazo "
                      f"({long_pct:+.1f}% entre el primer y último cuartil del período).")
    elif long_pct < -10:
        trend_text = (f"La serie histórica muestra una <b>tendencia decreciente</b> de largo plazo "
                      f"({long_pct:+.1f}% entre el primer y último cuartil del período).")
    else:
        trend_text = ("La serie histórica no presenta una tendencia marcada de largo plazo; "
                      "el nivel de incidencia se mantiene relativamente estable.")
    elems.append(Paragraph(trend_text, S['body']))

    # ── 2. Methodology note ───────────────────────────────────────────────────
    if is_agg:
        n_types = ctx.get('n_crime_types', '?')
        elems.append(Paragraph(
            f"Se aplicó el método <b>Bottom-Up</b>: cada uno de los {n_types} tipos de delito "
            f"fue modelado individualmente con el modelo más adecuado según su frecuencia "
            f"histórica (baja frecuencia → Tendencia Lineal; frecuencia media → Suavizamiento "
            f"Exponencial; alta frecuencia → mejor de los 4 modelos por DMA). "
            f"Los pronósticos individuales se sumaron para obtener el total del cantón. "
            f"Este enfoque preserva los patrones estacionales específicos de cada tipo de delito "
            f"y evita que distintos ciclos se cancelen entre sí.",
            S['body'],
        ))
    else:
        if best_key in ('seasonal_index', 'multiplicative_decomposition'):
            seasonal_list = ctx.get('best_seasonal_list', [])
            if seasonal_list:
                peak_month   = max(seasonal_list, key=lambda x: float(x['value']))
                trough_month = min(seasonal_list, key=lambda x: float(x['value']))
                trough_val   = float(trough_month['value'])
                if trough_val > 0:
                    ratio_text = (f"la incidencia en el mes pico es "
                                  f"{float(peak_month['value']) / trough_val:.1f}× "
                                  f"la del mes con menor actividad.")
                else:
                    ratio_text = (f"el mes {trough_month['month_name']} no registró eventos "
                                  f"en el período histórico (índice 0.0).")
                elems.append(Paragraph(
                    f"El análisis detectó un <b>patrón estacional significativo</b>. "
                    f"El mes de mayor incidencia relativa es <b>{peak_month['month_name']}</b> "
                    f"(índice {float(peak_month['value']):.2f}), mientras que "
                    f"{trough_month['month_name']} presenta la menor incidencia "
                    f"(índice {trough_val:.2f}). "
                    + ratio_text,
                    S['body'],
                ))
        else:
            elems.append(Paragraph(
                f"El modelo seleccionado ({best_method}) no modela estacionalidad explícita. "
                f"Si la serie presenta ciclos mensuales, considere analizar con "
                f"un período de datos mayor para habilitar los métodos estacionales.",
                S['body'],
            ))

    # ── 3. Forecast summary ───────────────────────────────────────────────────
    direction  = ('un incremento' if pct_change > 5 else
                  'una reducción' if pct_change < -5 else 'un nivel estable')
    fore_total = sum(fore_values) if fore_values else 0
    elems.append(Paragraph(
        f"Para los próximos <b>{n_months} meses</b>, el pronóstico proyecta {direction} "
        f"del {abs(pct_change):.1f}% en el total de delitos "
        f"en el cantón de {canton} "
        f"({recent_avg:.1f} eventos/mes → {fore_avg:.1f} proyectados). "
        f"El total acumulado proyectado para el período es de <b>{fore_total:,} eventos</b>.",
        S['body'],
    ))

    # ── 4. Model quality ──────────────────────────────────────────────────────
    if is_agg:
        elems.append(Paragraph(
            f"La metodología Bottom-Up produce pronósticos individuales para cada tipo de "
            f"delito; la calidad de ajuste varía por tipo. Consulte el desglose en la tabla "
            f"anterior para los valores de DMA por tipo de delito.",
            S['body'],
        ))
    else:
        acc_val = best_acc or 0
        mae_val = best_mae or 0
        quality = ('excelente' if acc_val >= 85 else 'aceptable' if acc_val >= 70 else 'limitada')
        elems.append(Paragraph(
            f"La precisión del modelo es <b>{quality}</b> ({acc_val:.1f}%). "
            f"El error absoluto medio de {mae_val:.2f} eventos/mes indica que las proyecciones "
            f"tienen una desviación promedio de {mae_val:.1f} eventos respecto a los datos reales "
            f"en el período de entrenamiento.",
            S['body'],
        ))

    # ── 5. Interpretation from service ───────────────────────────────────────
    if interpretation:
        clean = (interpretation
                 .replace('<strong>', '<b>').replace('</strong>', '</b>')
                 .replace('<em>', '<i>').replace('</em>', '</i>'))
        elems.append(Spacer(1, 6))
        elems.append(Paragraph(clean, S['note']))

    return elems


# ── Main entry point ──────────────────────────────────────────────────────────
def generate_forecast_pdf(context: dict) -> bytes:
    """
    Generate a professional executive PDF report from forecasting results.

    Args:
        context: dict returned by forecast_service.generate_forecast()

    Returns:
        PDF content as bytes.
    """
    is_agg = context.get('is_aggregated_forecast', False)

    # Normalise Bottom-Up context so all sections receive the keys they expect
    if is_agg:
        context = _normalize_bottom_up_for_pdf(context)

    # ── Pre-render matplotlib charts ──────────────────────────────────────────
    chart_series = None
    chart_mae    = None
    try:
        chart_series = _chart_series_forecast(context)
    except Exception as exc:
        logger.warning('Chart series/forecast failed: %s', exc)
    try:
        chart_mae = _chart_mae_comparison(context.get('metrics_comparison', []))
    except Exception as exc:
        logger.warning('Chart MAE failed: %s', exc)

    # ── Document setup ────────────────────────────────────────────────────────
    buffer = io.BytesIO()
    canton = context.get('canton', '').title()
    delito = context.get('delito', '').title()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T,
        bottomMargin=MARGIN_B,
        title=f'Pronóstico de Criminalidad — {canton} / {delito}',
        author='Sistema de Pronóstico de Criminalidad — UCR Sede de Occidente',
        subject=f'Reporte de pronóstico: {delito} en {canton}',
    )

    S = _styles()

    # ── Story assembly ────────────────────────────────────────────────────────
    story = []

    # Page 1 is the cover — drawn entirely via canvas callback.
    story.append(PageBreak())

    # Executive summary
    story.extend(_section_executive_summary(context, S))
    story.append(Spacer(1, 8))

    # Parameters
    story.extend(_section_parameters(context, S))
    story.append(Spacer(1, 8))

    # Historical + forecast chart and table
    story.extend(_section_historical_forecast(context, S, chart_series))

    if is_agg:
        # Bottom-Up: per-type breakdown replaces model comparison
        story.extend(_section_breakdown(context, S))
    else:
        # Standard: four-model comparison
        story.extend(_section_metrics(context, S, chart_mae))

    # Crime composition (for both all-crimes modes)
    story.extend(_section_composition(context, S))

    # Conclusions
    story.extend(_section_conclusions(context, S))

    # ── Build ─────────────────────────────────────────────────────────────────
    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_cover(c, d, context),
        onLaterPages=lambda c, d: _draw_content_page(c, d, context),
    )

    return buffer.getvalue()
