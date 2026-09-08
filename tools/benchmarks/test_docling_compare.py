"""Check score-affecting export behavior using actual Docling objects."""
import unittest
from docling_core.types.doc import DoclingDocument, TableData, TableCell, DocItemLabel
from tools.benchmarks.docling_compare import export_markdown, paddle_table_html

class ExportTests(unittest.TestCase):
    def test_paddle_otsl_merged_cells(self):
        text = '<fcel>A<lcel><fcel>B<nl><ucel><xcel><fcel>000123<nl>'
        output = paddle_table_html(text)
        self.assertIn('rowspan="2"', output)
        self.assertIn('colspan="2"', output)
        self.assertIn('000123', output)
        self.assertNotIn('<fcel>', output)

    def test_inline_latex_is_not_escaped_as_prose(self):
        doc = DoclingDocument(name='test')
        text = r'The term \(a_{rc}^{(2)} < b_1\) is nonzero.'
        doc.add_text(label=DocItemLabel.TEXT, text=text)
        self.assertIn(text, export_markdown(doc))

    def test_table_spans_and_precision_survive(self):
        doc = DoclingDocument(name='test')
        doc.add_table(data=TableData(num_rows=2, num_cols=2, table_cells=[
            TableCell(text='Merged', row_span=1, col_span=2, start_row_offset_idx=0,
                      end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=2),
            TableCell(text='000123', start_row_offset_idx=1, end_row_offset_idx=2,
                      start_col_offset_idx=0, end_col_offset_idx=1),
            TableCell(text='1.23456789', start_row_offset_idx=1, end_row_offset_idx=2,
                      start_col_offset_idx=1, end_col_offset_idx=2)]))
        md = export_markdown(doc)
        self.assertIn('colspan="2"', md)
        self.assertIn('000123', md)
        self.assertIn('1.23456789', md)

    def test_paddle_table_replaces_only_its_table(self):
        doc = DoclingDocument(name='test')
        doc.add_text(label=DocItemLabel.TEXT, text='before')
        table = doc.add_table(data=TableData(num_rows=0, num_cols=0, table_cells=[]))
        doc.add_text(label=DocItemLabel.TEXT, text='after')
        raw = '<table><tr><td rowspan="2">Paddle</td></tr></table>'
        md = export_markdown(doc, {table.self_ref: raw})
        self.assertIn(raw, md)
        self.assertLess(md.index('before'), md.index(raw))
        self.assertLess(md.index(raw), md.index('after'))

if __name__ == '__main__':
    unittest.main()
