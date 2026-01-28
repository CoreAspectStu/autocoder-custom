"""
PDF Export Utility for UAT Test Results

Generates professional PDF reports from test result data.
Feature #296: Export test results as PDF report
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
from typing import Dict, List, Any, Optional
import io
import logging

logger = logging.getLogger(__name__)


class PDFExporter:
    """
    Generate professional PDF reports from test results

    Features:
    - Professional layout with headers and footers
    - Test summary statistics
    - Detailed test results table
    - Color-coded pass/fail status
    - Multiple result filtering options
    """

    def __init__(self, page_size=A4):
        """
        Initialize PDF exporter

        Args:
            page_size: Page size for PDF (default: A4)
        """
        self.page_size = page_size
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles for the PDF"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f2937'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Subtitle style
        self.styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#6b7280'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica'
        ))

        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#374151'),
            spaceBefore=20,
            spaceAfter=10,
            fontName='Helvetica-Bold'
        ))

        # Normal text style
        self.styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#4b5563'),
            spaceAfter=12,
            fontName='Helvetica'
        ))

        # Pass status style
        self.styles.add(ParagraphStyle(
            name='StatusPass',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.green,
            fontName='Helvetica-Bold'
        ))

        # Fail status style
        self.styles.add(ParagraphStyle(
            name='StatusFail',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.red,
            fontName='Helvetica-Bold'
        ))

    def export_test_results(
        self,
        results: List[Dict[str, Any]],
        title: str = "UAT Test Results Report",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """
        Export test results as PDF

        Args:
            results: List of test result dictionaries
            title: Report title
            metadata: Optional metadata (test_run_id, date, etc.)

        Returns:
            PDF file as bytes
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.page_size,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        # Build PDF content
        story = []
        story.extend(self._build_header(title, metadata))
        story.append(Spacer(1, 0.2*inch))

        # Add summary section
        story.extend(self._build_summary_section(results))
        story.append(Spacer(1, 0.3*inch))

        # Add detailed results table
        story.extend(self._build_results_table(results))

        # Build PDF
        doc.build(story)

        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(f"Generated PDF report with {len(results)} test results")
        return pdf_bytes

    def _build_header(
        self,
        title: str,
        metadata: Optional[Dict[str, Any]]
    ) -> List:
        """Build PDF header with title and metadata"""
        story = []

        # Title
        story.append(Paragraph(title, self.styles['CustomTitle']))
        story.append(Spacer(1, 0.1*inch))

        # Subtitle with date
        date_str = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        subtitle = f"Generated on {date_str}"
        if metadata and 'test_run_id' in metadata:
            subtitle += f" • Test Run: {metadata['test_run_id']}"
        story.append(Paragraph(subtitle, self.styles['CustomSubtitle']))

        return story

    def _build_summary_section(self, results: List[Dict[str, Any]]) -> List:
        """Build summary statistics section"""
        story = []
        story.append(Paragraph("Test Summary", self.styles['SectionHeader']))

        # Calculate statistics
        total = len(results)
        passed = sum(1 for r in results if r.get('status') == 'passed')
        failed = sum(1 for r in results if r.get('status') == 'failed')
        skipped = sum(1 for r in results if r.get('status') == 'skipped')
        pass_rate = (passed / total * 100) if total > 0 else 0

        # Summary table
        summary_data = [
            ['Total Tests', str(total)],
            ['Passed', str(passed)],
            ['Failed', str(failed)],
            ['Skipped', str(skipped)],
            ['Pass Rate', f"{pass_rate:.1f}%"]
        ]

        summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1f2937')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ]))

        story.append(summary_table)
        return story

    def _build_results_table(self, results: List[Dict[str, Any]]) -> List:
        """Build detailed test results table"""
        story = []
        story.append(Paragraph("Detailed Results", self.styles['SectionHeader']))

        if not results:
            story.append(Paragraph("No test results available.", self.styles['CustomNormal']))
            return story

        # Table headers
        headers = ['Test Name', 'Status', 'Duration', 'Timestamp']

        # Build table data
        table_data = [headers]

        for result in results[:100]:  # Limit to 100 results for performance
            test_name = result.get('test_name', 'Unknown')
            status = result.get('status', 'unknown')
            duration = result.get('duration', 0)
            timestamp = result.get('timestamp', '')

            # Format duration
            duration_str = f"{duration:.2f}s" if isinstance(duration, (int, float)) else 'N/A'

            # Format timestamp
            if timestamp:
                try:
                    if isinstance(timestamp, str):
                        ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        timestamp_str = ts.strftime("%Y-%m-%d %H:%M")
                    else:
                        timestamp_str = str(timestamp)
                except:
                    timestamp_str = str(timestamp)[:16]
            else:
                timestamp_str = 'N/A'

            table_data.append([test_name, status.upper(), duration_str, timestamp_str])

        # Create table
        table = Table(table_data, colWidths=[3*inch, 1*inch, 1*inch, 1.5*inch])
        table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),

            # Data rows
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1f2937')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),

            # Status column color coding
            ('TEXTCOLOR', (1, 1), (1, -1), colors.HexColor('#1f2937')),
        ]))

        # Color-code status column
        for i, row in enumerate(table_data[1:], start=1):
            status = row[1].lower()
            if status == 'passed':
                table.setStyle(TableStyle([
                    ('TEXTCOLOR', (1, i), (1, i), colors.green),
                ]))
            elif status == 'failed':
                table.setStyle(TableStyle([
                    ('TEXTCOLOR', (1, i), (1, i), colors.red),
                ]))
            elif status == 'skipped':
                table.setStyle(TableStyle([
                    ('TEXTCOLOR', (1, i), (1, i), colors.HexColor('#f59e0b')),
                ]))

        story.append(table)

        # Add note if results were truncated
        if len(results) > 100:
            story.append(Spacer(1, 0.2*inch))
            note = Paragraph(
                f"Note: Showing first 100 of {len(results)} results.",
                self.styles['CustomNormal']
            )
            story.append(note)

        return story


def create_pdf_exporter() -> PDFExporter:
    """Factory function to create PDF exporter"""
    return PDFExporter()
