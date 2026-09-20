import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.Brep2Regin.extract_curve_edges import extract


XML = '''<?xml version="1.0"?>
<AutoConcept><Sections><Section><ID>1</ID><Name>S_1</Name><CoordSysID>1</CoordSysID></Section></Sections>
<Points>
 <Point><ID>1</ID><Name>S_1_SP_1</Name><Type>2</Type><sectionName>S_1</sectionName><gCoord><item>0</item><item>0</item><item>0</item></gCoord><sCoord><item>0</item><item>0</item><item>0</item></sCoord></Point>
 <Point><ID>2</ID><Name>S_1_SP_2</Name><Type>2</Type><sectionName>S_1</sectionName><gCoord><item>0</item><item>1</item><item>0</item></gCoord><sCoord><item>0</item><item>1</item><item>0</item></sCoord></Point>
 <Point><ID>3</ID><Name>S_1_SP_3</Name><Type>2</Type><sectionName>S_1</sectionName><gCoord><item>0</item><item>1</item><item>1</item></gCoord><sCoord><item>0</item><item>1</item><item>1</item></sCoord></Point>
 <Point><ID>4</ID><Name>S_1_SP_4</Name><Type>2</Type><sectionName>S_1</sectionName><gCoord><item>0</item><item>0</item><item>1</item></gCoord><sCoord><item>0</item><item>0</item><item>1</item></sCoord></Point>
 <Point><ID>4</ID><Name>S_1_SP_4_DUP</Name><Type>2</Type><sectionName>S_1</sectionName><gCoord><item>0</item><item>0</item><item>1</item></gCoord><sCoord><item>0</item><item>0</item><item>1</item></sCoord></Point>
</Points><Curves>
 <Curve><ID>1</ID><Name>S_1_SL_1</Name><Type>1</Type><sectionName>S_1</sectionName><startPointID>1</startPointID><startPointName>S_1_SP_1</startPointName><endPointID>2</endPointID><endPointName>S_1_SP_2</endPointName></Curve>
 <Curve><ID>2</ID><Name>S_1_SL_2</Name><Type>1</Type><sectionName>S_1</sectionName><startPointName>S_1_SP_2</startPointName><endPointName>S_1_SP_3</endPointName></Curve>
 <Curve><ID>3</ID><Name>S_1_SL_3</Name><Type>1</Type><sectionName>S_1</sectionName><startPointName>S_1_SP_3</startPointName><endPointName>S_1_SP_4</endPointName></Curve>
 <Curve><ID>4</ID><Name>S_1_SL_4</Name><Type>1</Type><sectionName>S_1</sectionName><startPointName>S_1_SP_4</startPointName><endPointName>S_1_SP_1</endPointName></Curve>
 <Curve><ID>5</ID><Name>S_1_SL_5</Name><Type>1</Type><sectionName>S_1</sectionName><startPointName>S_1_SP_2</startPointName><endPointName>S_1_SP_404</endPointName></Curve>
</Curves></AutoConcept>'''


class CurveEdgeExtractionTests(unittest.TestCase):
    def test_closed_branch_missing_and_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fixture.xml"
            p.write_text(XML, encoding="utf-8")
            data = extract(p)
        sec = data["sections"][0]
        self.assertEqual(sec["topology"]["classification"], "closed")
        self.assertEqual(sec["topology"]["component_count"], 1)
        self.assertEqual(sec["topology"]["branch_count"], 0)
        self.assertFalse(sec["curves"][-1]["endpoint_valid"])
        self.assertEqual(sec["curves"][-1]["topology_signature"], "missing_endpoint")
        self.assertTrue(any(d["code"] == "duplicate_point_id" for d in data["diagnostics"]))
        self.assertEqual(len(data["source"]["sha256"]), 64)

    def test_python_macro_open_chain(self):
        macro = """p1=theModel.createSecNode(x=0,y=0,z=0,theSect=S)\np2=theModel.createSecNode(x=0,y=1,z=0,theSect=S)\np3=theModel.createSecNode(x=0,y=2,z=0,theSect=S)\nc1=theModel.createSecCurve(start=p1,end=p2,theSect=S)\nc2=theModel.createSecCurve(start=p2,end=p3,theSect=S)\n"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "shape.py"
            p.write_text(macro, encoding="utf-8")
            sec = extract(p)["sections"][0]
        self.assertEqual(sec["topology"]["classification"], "open")
        self.assertEqual(len(sec["curves"]), 2)
        self.assertEqual(sec["curves"][0]["type"], "line")

    def test_branch_is_explicit(self):
        branch = XML.replace("</Curves>", " <Curve><ID>6</ID><Name>S_1_SL_6</Name><Type>1</Type><sectionName>S_1</sectionName><startPointName>S_1_SP_2</startPointName><endPointName>S_1_SP_4</endPointName></Curve></Curves>")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "branch.xml"
            p.write_text(branch, encoding="utf-8")
            sec = extract(p)["sections"][0]
        self.assertEqual(sec["topology"]["classification"], "branched")
        self.assertGreater(sec["topology"]["branch_count"], 0)

    def test_real_b_shape_is_read_only_and_has_scoped_bezier(self):
        p = Path(__file__).resolve().parents[1] / "sections" / "B-shape-2" / "B-shape-2.xml"
        before = hashlib.sha256(p.read_bytes()).hexdigest()
        data = extract(p)
        sec = data["sections"][0]
        self.assertEqual(len(sec["curves"]), 22)
        self.assertEqual(len(sec["points"]), 22)
        self.assertTrue(all(c["endpoint_valid"] for c in sec["curves"]))
        self.assertEqual(sec["curves"][0]["scope"]["section"], "S_1")
        self.assertEqual(len(sec["curves"][0]["control_points"]), 2)
        self.assertGreater(sec["curves"][0]["length"], 0)
        self.assertEqual(before, data["source"]["geometry_sha256"])
        self.assertEqual(before, hashlib.sha256(p.read_bytes()).hexdigest())

    def test_yaml_candidate_coordinates_use_bbox_origin(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / "shape.xml").write_text(XML, encoding="utf-8")
            path = directory / "shape.yaml"
            path.write_text("id: shape\nregions:\n  - name: wall\n    bbox: {x: 0.8, y: 0.2, width: 0.4, height: 0.6}\n", encoding="utf-8")
            sec = extract(path)["sections"][0]
        mapping = sec["region_candidates"][0]
        self.assertEqual(mapping["curve_ids"], ["2"])
        self.assertEqual(mapping["method"], "bbox_candidates_not_gold")


if __name__ == "__main__":
    unittest.main()
