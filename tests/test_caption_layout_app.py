from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from utils.ocr import layout_caption


def test_filter_requires_layout_and_confidence():
    texts = ["For you", "This caption is for you", "@artist"]
    boxes = [[[0,y],[w,y],[w,y+h],[0,y+h]] for y,w,h in [(1,18,4),(60,85,10),(95,15,4)]]
    assert layout_caption(texts, boxes, [.99]*3, (100,100)) == texts[1]
    assert layout_caption(texts, boxes, [.6,.99,.6], (100,100)) == "\n".join(texts)
    assert layout_caption(["For you"], boxes[:1], [.99], (100,100)) is None


def test_real_analysis_survives_streamlit_reruns():
    root = Path(__file__).resolve().parents[1]
    original = (root/"data/imported_images/wasting-potential.jpg").read_bytes()
    with patch("utils.intelligence_ui.st.file_uploader", return_value=BytesIO(original)), \
            patch("utils.images.load_preview", return_value=None):
        app = AppTest.from_file(str(root/"app.py"), default_timeout=90).run()
        app.button(key="v3_analyze").click().run()
        assert not app.exception
        result = app.session_state["v3_result"]
        assert result["identification"].mode == "exact pixels"
        assert "For you" in result["ocr"].text
        assert app.text_area(key="v3_text").value == "i love wasting my potential\nit's my favorite hobby"
        app.text_area(key="v3_text").set_value("My corrected caption").run()
        result["identification"].status = "possible"
        app.session_state["v3_revision"] = "previous build"
        app.run()
        assert app.session_state["v3_result"]["identification"].status == "likely"
        app.button(key="v3_explain").click().run()
        assert app.session_state["v3_explanation"].explanation.visible_text == "My corrected caption"
