import os
import json
import shutil
import tempfile
import subprocess
import pandas as pd
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import sys

app = FastAPI(title="Infiswift Solar Pipeline API")

# Define the absolute path to your main folder and integrator script
BASE_DIR = Path(__file__).resolve().parent
INTEGRATOR_SCRIPT = BASE_DIR / "integrated_code.py"
RESULTS_CSV = BASE_DIR / "simulation_results.csv" # The file your pipeline generates

@app.post("/api/run-pipeline")
async def run_pipeline(
    pdf_file: UploadFile = File(...),
    user_inputs: str = Form(...) # The backend will send the JSON inputs as a form string
):
    print(f"\n📥 Received API request for PDF: {pdf_file.filename}")
    
    # 1. Use a temporary directory so multiple API calls don't overwrite each other's files
    with tempfile.TemporaryDirectory() as temp_dir:
        
        # Save the uploaded PDF
        pdf_path = os.path.join(temp_dir, pdf_file.filename)
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(pdf_file.file, buffer)
            
        # Save the User Inputs JSON string to a file
        inputs_path = os.path.join(temp_dir, "user_inputs.json")
        try:
            parsed_inputs = json.loads(user_inputs)
            with open(inputs_path, "w", encoding='utf-8') as f:
                json.dump(parsed_inputs, f, ensure_ascii=False, indent=4)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format in user_inputs.")

        # 2. Trigger the integrated_code.py script
        print("🚀 Launching integration pipeline subprocess...")
        
        # We run it exactly as you would in the terminal
        process = subprocess.run(
            [sys.executable, str(INTEGRATOR_SCRIPT), "--pdf_path", pdf_path, "--user_inputs_json", inputs_path],
            cwd=str(BASE_DIR), # Ensure it runs in the Infiswift folder
            capture_output=True,
            text=True
        )

        # Print the logs to the API terminal so you can monitor what the bot is doing
        print("\n--- Pipeline Console Output ---")
        print(process.stdout)
        
        if process.returncode != 0:
            print("\n❌ --- Pipeline Errors ---")
            print(process.stderr)
            raise HTTPException(status_code=500, detail="Pipeline execution failed. Check server logs.")

        # 3. Read the output CSV and return it as JSON to the backend
        if not RESULTS_CSV.exists():
             raise HTTPException(status_code=500, detail="Pipeline succeeded but simulation_results.csv was not found.")
             
        try:
            # Convert the CSV results into a clean JSON list for the frontend/backend to use
            df = pd.read_csv(RESULTS_CSV)
            results_list = df.to_dict(orient="records")
            
            # Optionally grab the final revenue from the last row's cumulative math, or just return the table
            return JSONResponse(content={
                "status": "success",
                "message": "Pipeline completed successfully.",
                "data": results_list
            })
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse output CSV: {str(e)}")


# Quick health check endpoint
@app.get("/api/health")
def health_check():
    return {"status": "online", "message": "API Server is running and ready."}