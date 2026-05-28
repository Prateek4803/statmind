"""
ppap_generator.py
PPAP Package Generator — assembles Cap + SPC + GRR results into a
Part Submission Warrant (PSW) formatted PDF.

Add to main.py:
  from ppap_generator import generate_ppap_report
  app.include_router(ppap_router)
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import tempfile, os, datetime

ppap_router = APIRouter(prefix='/api/v1/ppap', tags=['ppap'])


class PPAPRequest(BaseModel):
    # Part info
    part_name: str
    part_number: str
    revision: str = "A"
    supplier_name: str = "StatMind User"
    customer_name: str = ""
    submission_reason: str = "Initial submission"

    # Attached analysis results (from previous sessions)
    capability_results: Optional[Dict[str, Any]] = None
    spc_results:        Optional[Dict[str, Any]] = None
    grr_results:        Optional[Dict[str, Any]] = None

    # Submission level
    level: int = 3  # PPAP Level 1-5


@ppap_router.post('/generate')
async def generate_ppap(body: PPAPRequest):
    """Generate a PPAP Part Submission Warrant PDF."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                         Paragraph, Spacer, HRFlowable)
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

        # ── Build PDF ─────────────────────────────────────────────────────────
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf',
                                           dir='/tmp/statmind_reports' if os.path.isdir('/tmp/statmind_reports') else tempfile.gettempdir())
        doc = SimpleDocTemplate(tmp.name, pagesize=letter,
                                  topMargin=0.5*inch, bottomMargin=0.5*inch,
                                  leftMargin=0.75*inch, rightMargin=0.75*inch)

        styles = getSampleStyleSheet()
        INDIGO = colors.HexColor('#6366f1')
        DARK   = colors.HexColor('#0b0d14')
        LIGHT  = colors.HexColor('#f0f2f0')
        GRAY   = colors.HexColor('#8b8fa8')

        title_style = ParagraphStyle('title', parent=styles['Title'],
                                      fontSize=18, textColor=INDIGO, spaceAfter=4)
        sub_style   = ParagraphStyle('sub', parent=styles['Normal'],
                                      fontSize=10, textColor=GRAY, spaceAfter=12)
        h2_style    = ParagraphStyle('h2', parent=styles['Heading2'],
                                      fontSize=12, textColor=DARK, spaceBefore=16, spaceAfter=6)
        body_style  = ParagraphStyle('body', parent=styles['Normal'], fontSize=9, leading=13)
        ok_style    = ParagraphStyle('ok', parent=styles['Normal'], fontSize=9,
                                      textColor=colors.HexColor('#34d980'))
        warn_style  = ParagraphStyle('warn', parent=styles['Normal'], fontSize=9,
                                      textColor=colors.HexColor('#f59e0b'))

        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        story = []

        # Header
        story.append(Paragraph('StatMind', ParagraphStyle('brand', parent=styles['Normal'],
                                                            fontSize=10, textColor=INDIGO)))
        story.append(Paragraph('Part Submission Warrant (PSW)', title_style))
        story.append(Paragraph(f'PPAP Level {body.level} · Generated {now} · statmind.tech', sub_style))
        story.append(HRFlowable(width='100%', thickness=1, color=INDIGO))
        story.append(Spacer(1, 12))

        # ── Part Information Table ─────────────────────────────────────────────
        story.append(Paragraph('Part Information', h2_style))
        part_data = [
            ['Part Name', body.part_name,         'Part Number', body.part_number],
            ['Revision',  body.revision,           'PPAP Level',  f'Level {body.level}'],
            ['Supplier',  body.supplier_name,      'Customer',    body.customer_name or '—'],
            ['Submission Reason', body.submission_reason, 'Date', now.split()[0]],
        ]
        t = Table(part_data, colWidths=[1.4*inch, 2.2*inch, 1.4*inch, 2.2*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8f9ff')),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#e8eaf0')),
            ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#e8eaf0')),
            ('FONTSIZE',   (0,0), (-1,-1), 9),
            ('FONTNAME',   (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTNAME',   (2,0), (2,-1), 'Helvetica-Bold'),
            ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor('#d0d4e8')),
            ('PADDING',    (0,0), (-1,-1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 16))

        # ── Capability Results ─────────────────────────────────────────────────
        story.append(Paragraph('Dimensional Results — Process Capability', h2_style))
        if body.capability_results:
            cap = body.capability_results
            cpk = cap.get('cpk', 'N/A')
            cp  = cap.get('cp', 'N/A')
            ppm = cap.get('ppm_within', 'N/A')
            verdict = cap.get('verdict', '')

            cap_data = [
                ['Metric', 'Value', 'Requirement', 'Status'],
                ['Cp',     str(round(cpk, 3)) if isinstance(cp, (int,float)) else cp,
                           '≥ 1.33', '✓ PASS' if isinstance(cp, (int,float)) and cp >= 1.33 else '✗ FAIL'],
                ['Cpk',    str(round(cpk, 3)) if isinstance(cpk, (int,float)) else cpk,
                           '≥ 1.33', '✓ PASS' if isinstance(cpk, (int,float)) and cpk >= 1.33 else '✗ FAIL'],
                ['PPM',    str(round(ppm, 1)) if isinstance(ppm, (int,float)) else ppm,
                           '< 233', '✓ PASS' if isinstance(ppm, (int,float)) and ppm < 233 else 'REVIEW'],
            ]
            ct = Table(cap_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            ct.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), INDIGO),
                ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
                ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0,0), (-1,-1), 9),
                ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor('#d0d4e8')),
                ('PADDING',    (0,0), (-1,-1), 6),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f9ff')]),
            ]))
            story.append(ct)
            if verdict:
                story.append(Spacer(1, 6))
                story.append(Paragraph(f'Verdict: {verdict}', body_style))
        else:
            story.append(Paragraph('⚠ No capability data attached. Run Capability Analysis first.', warn_style))

        story.append(Spacer(1, 16))

        # ── SPC Results ────────────────────────────────────────────────────────
        story.append(Paragraph('Statistical Process Control (SPC)', h2_style))
        if body.spc_results:
            spc = body.spc_results
            in_ctrl = spc.get('in_control', True)
            violations = spc.get('violations', [])
            chart_type = spc.get('chart_type', 'I-MR')
            story.append(Paragraph(
                f'Chart Type: {chart_type} | In Control: {"Yes ✓" if in_ctrl else "No ✗"} | '
                f'Violations: {len(violations)}', body_style))
            if violations:
                for v in violations[:5]:
                    story.append(Paragraph(f'  • {v}', warn_style))
        else:
            story.append(Paragraph('⚠ No SPC data attached. Run SPC Analysis first.', warn_style))

        story.append(Spacer(1, 16))

        # ── GRR Results ────────────────────────────────────────────────────────
        story.append(Paragraph('Measurement System Analysis (GRR)', h2_style))
        if body.grr_results:
            grr = body.grr_results
            grr_pct = grr.get('grr_percent_tv', None)
            ndc = grr.get('ndc', None)
            if grr_pct is not None:
                status = '✓ Acceptable' if grr_pct < 10 else ('Marginal' if grr_pct < 30 else '✗ Unacceptable')
                story.append(Paragraph(f'%GRR: {grr_pct:.1f}% | NDC: {ndc} | Status: {status}', body_style))
            else:
                story.append(Paragraph(str(grr), body_style))
        else:
            story.append(Paragraph('⚠ No GRR data attached. Run Gauge R&R first.', warn_style))

        story.append(Spacer(1, 20))

        # ── PPAP Checklist ─────────────────────────────────────────────────────
        story.append(Paragraph(f'PPAP Level {body.level} Requirements Checklist', h2_style))
        all_elements = [
            (1, 'Design Records'),
            (1, 'Engineering Change Documents'),
            (1, 'Customer Engineering Approval'),
            (2, 'Design FMEA'),
            (2, 'Process Flow Diagram'),
            (2, 'Process FMEA'),
            (2, 'Control Plan'),
            (3, 'Measurement System Analysis (GRR)'),
            (3, 'Dimensional Results'),
            (3, 'Material / Performance Test Results'),
            (3, 'Initial Process Study (Capability)'),
            (3, 'Qualified Laboratory Documentation'),
            (3, 'Appearance Approval Report'),
            (3, 'Sample Production Parts'),
            (3, 'Master Sample'),
            (3, 'Checking Aids'),
            (3, 'Customer-Specific Requirements'),
            (3, 'Part Submission Warrant'),
        ]
        checklist_data = [['#', 'Element', 'Required at Level', 'Status']]
        for i, (lvl, name) in enumerate(all_elements, 1):
            required = lvl <= body.level
            status = 'Required' if required else 'N/A'
            # Mark statmind-generated ones
            if 'Capability' in name and body.capability_results:
                status = '✓ Attached'
            elif 'GRR' in name and body.grr_results:
                status = '✓ Attached'
            elif 'SPC' in name or 'Process Study' in name:
                status = '✓ Attached' if body.spc_results else status
            elif 'Submission Warrant' in name:
                status = '✓ This Document'
            checklist_data.append([str(i), name, f'Level {lvl}+', status])

        cl = Table(checklist_data, colWidths=[0.4*inch, 3.2*inch, 1.2*inch, 1.5*inch])
        cl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), INDIGO),
            ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
            ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',   (0,0), (-1,-1), 8),
            ('GRID',       (0,0), (-1,-1), 0.3, colors.HexColor('#d0d4e8')),
            ('PADDING',    (0,0), (-1,-1), 5),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f9ff')]),
        ]))
        story.append(cl)

        story.append(Spacer(1, 20))
        story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY))
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f'Generated by StatMind · statmind.tech · {now} · '
            f'This document was auto-generated and should be reviewed by a qualified engineer before submission.',
            ParagraphStyle('footer', parent=styles['Normal'], fontSize=7, textColor=GRAY, alignment=TA_CENTER)
        ))

        doc.build(story)
        tmp.close()

        filename = f"PPAP_PSW_{body.part_number}_{body.revision}_{datetime.date.today().isoformat()}.pdf"
        return FileResponse(tmp.name, media_type='application/pdf',
                            filename=filename,
                            headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@ppap_router.get('/template')
async def ppap_template():
    """Return empty PPAP template structure."""
    return {
        "part_name": "",
        "part_number": "",
        "revision": "A",
        "supplier_name": "",
        "customer_name": "",
        "submission_reason": "Initial submission",
        "level": 3,
        "capability_results": None,
        "spc_results": None,
        "grr_results": None,
        "levels_description": {
            1: "Warrant only",
            2: "Warrant + limited supporting data",
            3: "Warrant + full supporting data (most common)",
            4: "Warrant + other requirements defined by customer",
            5: "Warrant + full supporting data reviewed at supplier's facility",
        }
    }
