"""
Optional one-off tool to (re)download CAISO carbon data from the WattTime API.
NOT required for the demo — the repo already ships
`watttime_carbon_data_CAISO_NORTH.csv`. Requires an extra dependency that is
intentionally NOT in requirements.txt:  pip install watttime
"""
import os
import argparse
from datetime import datetime
try:
    from watttime import WattTimeHistorical, WattTimeMyAccess
except ImportError:
    print("Error: The 'watttime' package is not installed.")
    print("Please install it using: pip install watttime")
    exit(1)

def register_watttime(username, password, email, org):
    """Register for a free WattTime account."""
    print(f"Registering new account for {username}...")
    wt = WattTimeMyAccess(username=username, password=password)
    try:
        wt.register(email=email, organization=org)
        print("✅ Registration successful!")
    except Exception as e:
        print(f"❌ Registration failed: {e}")

def download_data(username, password, start_date, end_date, region="CAISO_NORTH"):
    """Download historical carbon intensity data."""
    print(f"\nDownloading historical data for {region} from {start_date} to {end_date}...")
    
    # If using environment variables, username and password can be None
    wt_hist = WattTimeHistorical(username=username, password=password)
    
    try:
        df = wt_hist.get_historical_pandas(
            start=f"{start_date} 00:00Z",
            end=f"{end_date} 00:00Z",
            region=region,
            signal_type="co2_moer"
        )
        
        # Save to csv in current directory
        output_file = f"watttime_carbon_data_{region}.csv"
        df.to_csv(output_file, index=False)
        print(f"✅ Download complete! Saved to: {os.path.abspath(output_file)}")
        print(df.head())
        
    except Exception as e:
        print(f"❌ Download failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download historical carbon data from WattTime.")
    parser.add_argument("--register", action="store_true", help="Register a new WattTime account")
    parser.add_argument("--user", type=str, help="WattTime Username", default=os.getenv("WATTTIME_USER"))
    parser.add_argument("--pass", dest="password", type=str, help="WattTime Password", default=os.getenv("WATTTIME_PASSWORD"))
    parser.add_argument("--email", type=str, help="Email for registration")
    parser.add_argument("--org", type=str, help="Organization for registration", default="University Student")
    
    parser.add_argument("--start", type=str, help="Start Date (YYYY-MM-DD)", default="2024-01-01")
    parser.add_argument("--end", type=str, help="End Date (YYYY-MM-DD)", default="2024-02-01")
    parser.add_argument("--region", type=str, help="Grid Region", default="CAISO_NORTH")

    args = parser.parse_args()

    if not args.user or not args.password:
        print("Error: Please provide --user and --pass, or set WATTTIME_USER and WATTTIME_PASSWORD environment variables.")
        exit(1)

    if args.register:
        if not args.email:
            print("Error: --email is required for registration.")
            exit(1)
        register_watttime(args.user, args.password, args.email, args.org)

    # Proceed to download
    download_data(args.user, args.password, args.start, args.end, args.region)
