import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
import json

# Add internal modules to pythonpath
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
sys.path.append(str(BASE_DIR / "price_calculator"))
sys.path.append(str(BASE_DIR / "pdf_extraction"))

# Safe imports
try:
    # Notice we removed the data_extractor import! That runs on its own schedule now.
    from pdf_extraction.input_parser_maxifit import run_extraction as extract_pdf
    from price_calculator.price_calci_simulator import run_simulation_pipeline 
except ImportError as e:
    print(f"Initialization Error: Ensure all inner modules are accessible. {e}")
    sys.exit(1)

def run_integration_pipeline(pdf_path: str, user_inputs_json: str = None):
    target_pdf = Path(pdf_path).resolve()
    
    if not target_pdf.exists():
        print(f"\n❌ Error: Target PDF file not found at: {target_pdf}")
        return

    print("\n" + "="*60)
    print(" 1. DATA EXTRACTOR (Skipped - Handled via Background SQL Updates) ")
    print("="*60)
    print("MySQL Database is acting as the single source of truth.")
    
    print("\n" + "="*60)
    print(" 2. PDF EXTRACTION & PARSING ")
    print("="*60)

    pdf_filename = target_pdf.name
    extracted_json_path = extract_pdf(str(target_pdf),pdf_filename)
    
    if not extracted_json_path or not os.path.exists(extracted_json_path):
        print("\n❌ Error: PDF extraction failed or no output config produced.")
        return
        
    print(f"✅ Maxifit configuration successfully generated: {extracted_json_path}")
        
    print("\n" + "="*60)
    print(" 3. MAXIFIT APP AUTOMATION ")
    print("="*60)
    demo_automation_script = BASE_DIR / "maxifit_automation" / "demo-automation.py"
    
    print("Launching pywinauto robotic simulation in dedicated subprocess...")
    automation_process = subprocess.run(
        [sys.executable, str(demo_automation_script), str(extracted_json_path)],
        cwd=str(BASE_DIR)
    )
    
    if automation_process.returncode != 0:
        print(f"\n⚠️ Warning: Maxifit Automation reported non-zero exit code ({automation_process.returncode}).")
    else:
        print("\n✅ Maxifit Automation Completed Successfully.")
    
    print("\n" + "="*60)
    print(" 4. FINANCIAL PRICING SIMULATION ")
    print("="*60)

    # Default Inputs. Hardcoded for now.
    user_inputs = {
        'region': '中部',
        'ex_ac': 1000.00,
        'ex_dc': 1127.80,
        'rep_ac': 1000.00,
        'rep_dc': 1421.28,
        'ex_yield': 1433741.0,   
        'rep_yield': 2182388.74, 
        'ex_deg': 0.007,
        'rep_deg': 0.004,
        'fit_price': 32.0,
        'latest_price': 8.9,
        'op_start_date': datetime(2016, 8, 31),
        'mod_date': datetime(2025, 7, 31),
    }

    if user_inputs_json and os.path.exists(user_inputs_json):
        print(f"Loading custom user inputs from JSON: {user_inputs_json}")
        try:
            with open(user_inputs_json, 'r', encoding='utf-8') as f:
                loaded_inputs = json.load(f)
                user_inputs.update(loaded_inputs)
                
                # Coerce dates back to datetimes for simulator component
                for date_key in ['op_start_date', 'mod_date']:
                    if date_key in user_inputs and isinstance(user_inputs[date_key], str):
                        try:
                            # Assume ISO equivalent format 'YYYY-MM-DD'
                            user_inputs[date_key] = datetime.strptime(user_inputs[date_key], '%Y-%m-%d')
                        except Exception as de:
                            print(f"Failed to parse datetime for {date_key}: {de}")
        except Exception as e:
            print(f"Failed to load user_inputs_json: {e}")
    else:
        print("Using default fallback user_inputs mapping...")
        
    try:
        # THE FIX: We just pass user_inputs. No more config_dict!
        run_simulation_pipeline(user_inputs)
        print("\n✅ Financial calculations completed successfully.")
    except Exception as e:
        print(f"\n❌ Error during Pricing Simulation: {e}")

    print("\n" + "="*60)
    print(" 🎉 PIPELINE EXECUTION COMPLETE ")
    print("="*60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full Solar Pipeline Integrator")
    parser.add_argument("--pdf_path", type=str, help="Absolute or relative path to the Project PDF.", required=True)
    parser.add_argument("--user_inputs_json", type=str, help="Absolute or relative path to JSON file containing dynamic Price Calculator inputs.", default=None)
    
    args = parser.parse_args()
    run_integration_pipeline(
        pdf_path=args.pdf_path,
        user_inputs_json=args.user_inputs_json
    )