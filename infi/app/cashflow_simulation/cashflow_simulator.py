import pandas as pd
import json
from datetime import datetime
from sqlalchemy import create_engine
from pathlib import Path
import os
class SolarSimulator:
    def __init__(self, db_url):
        self.engine=create_engine(db_url)
        #default fallback incase we hit db error
        self.reference_prices = {}
        self.balancing_costs = [0.0] * 20
        self.ppa_prices = {}
        self.non_fossil_value = 0.6
        self.load_from_db()
    def load_from_db(self):
        print("Fetching simulation constants from MySQL...")
        try:
            #----1.Reference price-----
            # match region column and return value of last available column
            df_ref=pd.read_sql_table('reference_price',con=self.engine)
            if not df_ref.empty and '集計' in df_ref.columns:
                last_col=df_ref.columns[-1]
                self.reference_prices=df_ref.set_index('集計')[last_col].to_dict()
            
            #----2. non fossil value----
            # returns the last row value of the '加重平均値' column
            df_nf=pd.read_sql_table("non_fossil",con=self.engine)
            if not df_nf.empty and '加重平均値' in df_nf.columns:
                self.non_fossil_value=float(df_nf['加重平均値'].dropna().iloc[-1])

            #----3. balancing costs----
            df_bal=pd.read_sql_table("balancing_cost",con=self.engine)
            if not df_bal.empty and df_bal.shape[1]>1:
                self.balancing_costs=df_bal.iloc[:,1].dropna().astype(float).tolist()

            #----4. PPA price----
            # match the regions in col[0] and return the respective col[1]
            df_ppa=pd.read_sql_table("ppa_price",con=self.engine)
            if not df_ppa.empty and df_ppa.shape[1]>1:
                col_0=df_ppa.columns[0]
                col_1=df_ppa.columns[1]
                self.ppa_prices=df_ppa.set_index(col_0)[col_1].to_dict()

        except Exception as e:
            print(f"⚠️ Warning: Could not load some tables from MySQL. Using defaults. Error: {e}")


    def month_diff(self, d1, d2):
        return (d2.year - d1.year) * 12 + d2.month - d1.month

    def run_simulation(self, params):
        fit_remaining_months = 20 * 12 - self.month_diff(params['op_start_date'], params['mod_date'])
        base_price_a = (params['fit_price'] * params['ex_dc'] + 
                        params['latest_price'] * (params['rep_dc'] - params['ex_dc'])) / params['rep_dc']
        
        ref_price_b = self.reference_prices.get(params['region'], 0.0)
        
        # Override with parameter non_fossil_value if provided, otherwise use extracted config
        non_fossil_val_c = params.get('non_fossil_value', self.non_fossil_value)
        ppa_price = self.ppa_prices.get(params['region'], 14.0)
        
        results = []
        cumulative_revenue = 0.0
        gen_kwh = params['rep_yield']
        
        for year in range(1, 21):
            # Safe boundary check: if length becomes more -default to 0.30
            bal_cost_d = self.balancing_costs[year - 1] if (year - 1) < len(self.balancing_costs) else 0.30
            
            fip_premium = base_price_a - ref_price_b - non_fossil_val_c + bal_cost_d 
            #fip_premium = 27.23008274 - 8.540559352 - 0.6 + bal_cost_d #---> gives same value
            months_at_end_of_year = year * 12
            months_at_start_of_year = (year - 1) * 12
            
            if months_at_end_of_year <= fit_remaining_months:
                sell_price = ppa_price + fip_premium
            elif months_at_start_of_year < fit_remaining_months:
                fip_months = fit_remaining_months - months_at_start_of_year
                non_fip_months = months_at_end_of_year-fit_remaining_months
                sell_price = ((ppa_price + fip_premium) * fip_months + ppa_price * non_fip_months) / 12.0
            else:
                sell_price = ppa_price
                
            revenue = gen_kwh * sell_price
            cumulative_revenue += revenue
            
            results.append({
                'Year': year,
                'Balancing_Cost_JPY_kWh': bal_cost_d,
                'FIP_Premium_JPY_kWh': fip_premium,
                'Sell_Price_JPY_kWh': sell_price,
                'Generation_kWh': gen_kwh,
                'Revenue_JPY': revenue
            })
            
            # Next year generation decreases based on Degradation rate
            gen_kwh = gen_kwh * (1.0 - params['rep_deg'])
            
        df = pd.DataFrame(results)
        
        summary = {
            'FIT_Remaining_Months': fit_remaining_months,
            'FIT_Remaining_Years': fit_remaining_months / 12.0,
            'Base_Price_A': base_price_a,
            'Reference_Price_B': ref_price_b,
            'Non_Fossil_Value_C': non_fossil_val_c,
            'PPA_Price': ppa_price,
            'Total_Revenue_20Y_JPY': cumulative_revenue
        }
        
        return df, summary

def run_simulation_pipeline(user_inputs: dict, csv_path: str = None) -> tuple:
    print(f"Initializing Solar Simulator... {'(Reading ' + Path(csv_path).name + ')' if csv_path else ''}")
    CALC_DIR = Path(__file__).resolve().parent.parent
    
    db_file_path = CALC_DIR / "priceCalci_portable.db"
    
    db_url = f"sqlite:///{db_file_path}"

    sim = SolarSimulator(db_url)
    
    # --- MAXIFIT CSV EXTRACTION HOOK ---
    if csv_path and os.path.exists(csv_path):
        try:
            # Read CSV without treating the first row as headers
            df_maxifit = pd.read_csv(csv_path, encoding='utf-8-sig', header=None, names=range(20))            
            for idx, row in df_maxifit.iterrows():
                label = str(row[0])
                
                # Extract AC Capacity
                if "総定格出力" in label:
                    user_inputs['rep_ac'] = float(row[1])
                
                # Extract DC Capacity
                elif "パネル総出力" in label:
                    user_inputs['rep_dc'] = float(row[1])
                
                # Extract Annual Generation Yield (Very last number in the row)
                elif "年間発電量" in label:
                    yield_values = row.dropna().values[1:] 
                    if len(yield_values) > 0:
                        user_inputs['rep_yield'] = float(yield_values[-1])

            print(f"   ↳ Extracted parameters: AC={user_inputs['rep_ac']}, DC={user_inputs['rep_dc']}, Yield={user_inputs['rep_yield']}")
            
        except Exception as e:
            print(f"   ⚠️ Failed to parse MaxiFit CSV: {e}")
            
    # Run the financial math with the newly updated user_inputs
    df, summary = sim.run_simulation(user_inputs)
    
    # Save the result to CSV dynamically based on the input name
    if csv_path:
        input_path = Path(csv_path)
        out_csv = str(input_path.parent / f"financial_{input_path.name}")
    else:
        out_csv = "simulation_results.csv"
        
    df.to_csv(out_csv, index=False, encoding='utf-8-sig')
    print(f"   ✅ Financial export saved to: {Path(out_csv).name}\n")
    
    return df, summary

if __name__ == "__main__":
    from datetime import datetime
    example_inputs = {
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
    
    # Test run
    run_simulation_pipeline(example_inputs)