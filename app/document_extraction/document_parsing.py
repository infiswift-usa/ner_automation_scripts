import os

# Workaround: Hugging Face Hub uses symlinks by default; Windows without Developer Mode fails.
# Set before any huggingface/docling imports to reduce cache errors on Windows.
if "HF_HUB_DISABLE_SYMLINKS_WARNING" not in os.environ:
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import json
import base64
from pathlib import Path
import io
from typing import TypedDict, List, Optional, Dict, Any
from dotenv import load_dotenv
# Docling Imports
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
# LangChain / LangGraph Imports
from langgraph.graph import StateGraph, END
from langgraph.types import RetryPolicy
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
# Load API Key
load_dotenv()
import numpy as np
import re
import pandas as pd

# ==========================================
# STRICT PYDANTIC SCHEMAS (JSON Structure)
# ==========================================
class ProjectInfo(BaseModel):
    project_name: str = Field(..., description="Project name extracted from the filename.")
    date: str = Field(..., description="Date of the drawing (e.g., '2025.01.05').")
    drawing_number: str = Field(..., description="Drawing number (e.g., 'RP-0042-SL01-00').")
    
    raw_location_text: str = Field(..., description="Extract the exact location string written in the bottom right corner of the drawing (e.g., '-三重県津市-').")
    prefecture: str = Field(..., description="Extract just the prefecture name from the location text (e.g., '三重県').")
    subregion: str = Field(..., description="Extract the core city, town, or village name. IGNORING and STRIPPING OFF the prefecture, the district name , or trailing suffix . Examples: '長野県上伊那郡飯島町' -> '飯島'. '三重県津市' -> '津'. '鹿児島県薩摩川内市' -> '薩摩川内'.")

class SolarModuleSpec(BaseModel):
    model_number: str = Field(..., description="Model number of the solar module (e.g., 'NER132M625E-NGD')")
    nominal_maximum_output_w: float = Field(..., description="公称最大出力 in W (e.g., 625)")

class PVArrayConfig(BaseModel):
    """Directly structured for the MaxiFit Automation Script"""
    pcs_group_name: str = Field(..., description="Original name from the document (e.g., 'PCS 01~04 (4台)')")
    pcs_type: str = Field(..., description="Map the PCS model. E.g., 'SG100CX-JP' -> 'SunGrow SG100CX-JP', 'SUN2000-50KTL' -> 'HUAWEI SUN2000-50KTL-NHK3'")
    module_type: str = Field(..., description="Model number of the solar module used (e.g., 'NER132M625E-NGD')")
    modules_per_string: int = Field(..., description="Number of modules in series (直列枚数) (e.g., 16)")
    strings: int = Field(..., description="Number of strings per PCS (系統数) (e.g., 14)")
    tilt: int = Field(..., description="Tilt angle for this specific array (e.g., 20).")
    # Force the model to think out loud before it answers
    direction_reasoning: str = Field(..., description="Scan horizontally from left to right exactly across the degree text (e.g., '11°' or '5°'). Tell me the exact order of the visual elements from left to right. You MUST output one of these two phrases: 'Order: Plain Line -> Text -> Diamond Line' OR 'Order: Diamond Line -> Text -> Plain Line'..")
    #direction: int = Field(..., description="Azimuth angle as an integer. Use POSITIVE numbers for Left tilts of north arrow, and NEGATIVE numbers for Right tilts of north arrow. (e.g., if north arrow is x degree to right return -x or if north arrow is y degree to left return y).")
    azimuth: int = Field(..., description="Azimuth angle as an integer. If your reasoning order is 'Plain Line -> Text -> Diamond Line', the arrow is tilted RIGHT, so output a NEGATIVE number (e.g., -11). If your reasoning order is 'Diamond Line -> Text -> Plain Line', the arrow is tilted LEFT, so output a POSITIVE number (e.g., 11). If perfectly vertical, output 0.")
    backside_efficiency: int = Field(0, description="Always set to 0 unless specified.")
    pcs_count: int = Field(..., description="Number of PCS units in this group (e.g., extract 4 from '4台').")

class AreaDetails(BaseModel):
    area_name: str = Field(..., description="Name of the area.")
    pv_arrays: List[PVArrayConfig] = Field(..., description="List of PV arrays (PCS groups) within this area formatted for MaxiFit.")

class BlueprintExtraction(BaseModel):
    project_information: ProjectInfo
    module_specifications: SolarModuleSpec
    area_breakdown: List[AreaDetails] = Field(..., description="List of all areas and their PV array configurations.")

# ==========================================
# STATE DEFINITION
# ==========================================
class ExtractionState(TypedDict):
    val_pdf_path: str
    raw_markdown: str
    page_images: List[str] 
    structured_data: dict
    error: str

subregion_map={
    "津市": "津",
    "上伊那郡飯島町": "飯島",
    "薩摩川内市": "川内",
    "三重郡": "四日市"
} #backup

PCS_MAP ={ 
    "SG100CX-JP": "SunGrow SG100CX-JP"
}

# ==========================================
# NODES
# ==========================================
def parse_document(state: ExtractionState):
    print(f"⚡ Parsing PDF & Capturing Diagrams: {state['val_pdf_path']}")
    
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False 
    pipeline_options.do_table_structure = True 
    pipeline_options.generate_page_images = True
    
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend
            )
        }
    )
    
    result = converter.convert(state['val_pdf_path'])
    markdown_text = result.document.export_to_markdown()
    
    images = []
    for page in result.pages:
        if page.image:
            buffered = io.BytesIO()
            page.image.save(buffered, format="JPEG", quality=85)
            img_str = base64.b64encode(buffered.getvalue()).decode()
            images.append(img_str)
            
    return {"raw_markdown": markdown_text, "page_images": images}

def route_after_parsing(state: ExtractionState):
    if state.get("error"): return END
    return "extractor"


def _build_extraction_message(state: ExtractionState) -> list:
    filename_hint = os.path.splitext(os.path.basename(state["val_pdf_path"]))[0]
    content: list = [
        {
            "type": "text",
            "text": f"""Analyze this solar blueprint. 
            
            CRITICAL INSTRUCTIONS:
            1. The file name is '{filename_hint}'. Use this for the project name.
            2. LOCATION: Find location in bottom right corner. Seperate the 'prefecture' and 'subregion' (eg., in '三重県津市' as '三重県','津市') EXACTLY as written.
            3. AZIMUTH MAPPING: To determine the 'azimuth_angle', examine the compass rose. North arrow is the line with the diamond tip.
                - If the True North arrow is tilted to the LEFT of the vertical line: Output a POSITIVE integer (e.g., 5).
                - If the True North arrow is tilted to the RIGHT of the vertical line: Output a NEGATIVE integer (e.g., -11).
                - If the True North arrow is perfectly vertical and aligned with the crosshairs with NO numeric degree offset written next to it, you MUST return '0 degrees'. 
                - DO NOT guess a degree if none is written. 
            4. NUM ARRAYS: For 'num_arrays', extract the integer number of units from the PCS text (eg., extract 4 from 'PCS 01~04(4台)' since it has 4 pcs)

            
            MARKDOWN EXTRACT:
            {state['raw_markdown']}""",
        }
    ]
    for img_data in state["page_images"]:
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}}
        )
    return [HumanMessage(content=content)]


# ==========================================
# SIMULATOR
# ==========================================

def _normalize_project_name(raw_name: str) -> str:
    """Extracts trailing name segment from full filename strings.
    e.g. 'モジュール配置図_RP-0039-SL01-00_Mie Tsu' -> 'Mie Tsu'
    """
    parts = raw_name.rsplit("_", 1)
    return parts[-1].strip() if len(parts) > 1 else raw_name.strip()


def _repo_root() -> Path:
    """windows_maxifit repo root (parent of ``app/``); used for bundled ``specs/manifest.csv``."""
    return Path(__file__).resolve().parents[2]


def _normalize_path(path: str | Path) -> Path:
    """Resolve *path* (relative to CWD or absolute, ``~`` expanded)."""
    return Path(path).expanduser().resolve()


# Fixed location in this repo (see specs/manifest.csv)
MANIFEST_PATH = _repo_root() / "specs" / "manifest.csv"


class DocumentParser:
    """LangGraph + Docling pipeline for blueprint PDFs; builds MaxiFit JSON payloads."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        self._llm = ChatGoogleGenerativeAI(
            model="gemini-3-pro-preview",
            api_key=os.environ.get("GOOGLE_API_KEY"),
            temperature=0,
        ).with_structured_output(BlueprintExtraction)

        def extraction_node(state: ExtractionState):
            print("🧠 Reasoning over Text + Diagrams...")
            try:
                out = self._llm.invoke(_build_extraction_message(state))
                return {"structured_data": out.model_dump()}
            except Exception as e:
                print(f"❌ Extraction Error: {e}")
                return {"error": str(e)}

        retries = RetryPolicy(max_attempts=3, initial_interval=2.0)
        workflow = StateGraph(ExtractionState)
        workflow.add_node("parser", parse_document)
        workflow.add_node("extractor", extraction_node, retry_policy=retries)
        workflow.set_entry_point("parser")
        workflow.add_conditional_edges("parser", route_after_parsing)
        workflow.add_edge("extractor", END)
        self._app = workflow.compile()
        self._manifest_path = manifest_path if manifest_path is not None else MANIFEST_PATH

    def parse(
        self,
        *pdf_paths: str | Path,
        output_directory: str | Path,
    ) -> list[str | None]:
        """Run extraction for one or more PDFs; write MaxiFit JSON per file under ``output_directory``.

        Paths follow normal rules: relative to the process current working directory unless absolute.
        """
        if not pdf_paths:
            return []
        output_dir = _normalize_path(output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[str | None] = []
        for pdf in pdf_paths:
            results.append(
                self._extract_one(_normalize_path(pdf), output_dir),
            )
        return results

    def _extract_one(
        self,
        pdf_file_path: Path,
        output_dir: Path,
    ) -> str | None:
        pdf_source_name = pdf_file_path.name
        if not pdf_file_path.exists():
            print(f"❌ File not found: {pdf_file_path}")
            return None

        initial_input: ExtractionState = {
            "val_pdf_path": str(pdf_file_path),
            "raw_markdown": "",
            "page_images": [],
            "structured_data": {},
            "error": "",
        }
        final_state = self._app.invoke(initial_input)
        if final_state.get("error"):
            print(f"❌ Extraction failed: {final_state['error']}")
            raise RuntimeError(final_state["error"])

        #print("\n✅ Final Extracted JSON:")
        #print(json.dumps(final_state["structured_data"], indent=4, ensure_ascii=False))
        extracted_json = final_state["structured_data"]
        project_name = _normalize_project_name(extracted_json["project_information"]["project_name"])

        raw_pref = extracted_json["project_information"]["prefecture"]
        raw_subreg = extracted_json["project_information"]["subregion"]
        mapped_subreg = raw_subreg

        try:
            df_manifest = pd.read_csv(self._manifest_path, encoding="utf-8")
            valid_ar = df_manifest[
                df_manifest["area"].str.contains(raw_pref, na=False)
                | df_manifest["area"].apply(lambda x: str(x) in raw_pref)
            ]
            valid_pnt = valid_ar["point"].unique()
            for point in valid_pnt:
                if point in raw_subreg:
                    mapped_subreg = point
                    print("success")
                    break
            if mapped_subreg == raw_subreg:
                for key, val in subregion_map.items():
                    if key in raw_subreg:
                        mapped_subreg = val
                        print("failed")
                        break
        except Exception as e:
            print(f"⚠️ Warning: Dynamic subregion matching failed ({e}).")

        flat_pv_arrays = []
        for area in extracted_json["area_breakdown"]:
            for array in area["pv_arrays"]:
                raw_pcs = array["pcs_type"]
                for key, val in PCS_MAP.items():
                    if key in raw_pcs:
                        array["pcs_type"] = val
                        break
                array.pop("pcs_group_name", None)
                array.pop("direction_reasoning", None)
                flat_pv_arrays.append(array)

        maxifit_payload = {
            "source": pdf_source_name,
            "location": {
                "area": extracted_json["project_information"]["prefecture"],
                "point": mapped_subreg,
            },
            "system_efficiency": 95,
            "power_efficiency": 1.0,
            "pcs_config": flat_pv_arrays,
            "output_files": {
                "output_directory": str(output_dir),
                "csv_filename": f"MAXIFIT_csv_output_{project_name}",
                "print_filename": f"MAXIFIT_output_print_{project_name}",
                "config_filename": f"MAXIFITconfig_{project_name}",
                "overwrite_existing": False,
            },
        }
        json_filename = output_dir / f"{project_name}_extracted.json"
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(maxifit_payload, f, indent=4, ensure_ascii=False)
        print(f"✅ JSON saved to: {json_filename}")
        return str(json_filename)


_default_parser: DocumentParser | None = None


def _get_default_parser() -> DocumentParser:
    global _default_parser
    if _default_parser is None:
        _default_parser = DocumentParser()
    return _default_parser


def run_extraction(
    pdf_file_path: str,
    output_directory: str | Path,
) -> str | None:
    """Runs the PDF extraction process and returns the path to the saved JSON config.

    output_directory: where to write the extracted JSON and the path recorded in
    maxifit_payload.output_files.output_directory.
    """
    results = _get_default_parser().parse(pdf_file_path, output_directory=output_directory)
    return results[0] if results else None

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract MaxiFit config from a plant PDF.")
    parser.add_argument(
        "pdf",
        nargs="*",
        default=None,
        help="Path to PDF (relative to current working directory unless absolute); multiple words are joined "
        "(unquoted paths with spaces). Default: input/plant_files sample blueprint.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("outputs") / "document_extraction",
        help="Directory for extracted JSON and MaxiFit output_files paths (created if missing).",
    )
    args = parser.parse_args()

    if not args.pdf:
        default_name = "モジュール配置図_RP-0039-SL01-00_Mie Tsu.pdf"
        pdf_arg = Path("input") / "plant_files" / default_name
    else:
        pdf_arg = Path(" ".join(args.pdf))

    try:
        _get_default_parser().parse(pdf_arg, output_directory=args.output)
    except RuntimeError as e:
        print(f"❌ Extraction failed: {e}")
        raise SystemExit(1) from e