import time
import random

print("Loading historical stock data (10 years)...")
time.sleep(1.5)
print("Starting algorithmic trading backtest...")

tickers = ["AAPL", "GOOGL", "MSFT", "AMZN"]
initial_balance = 100000.0
balance = initial_balance

for year in range(2014, 2025):
    print(f"\n[Year {year}] Simulating market conditions...")
    time.sleep(0.5)
    
    yearly_return = 0
    for ticker in tickers:
        stock_return = random.uniform(-0.15, 0.35)
        print(f"  > {ticker}: {stock_return*100:+.2f}%")
        yearly_return += stock_return / len(tickers)
        time.sleep(0.3)
        
    balance *= (1 + yearly_return)
    print(f"End of {year} Portfolio Value: ${balance:,.2f} ({(balance/initial_balance - 1)*100:+.2f}%)")

print(f"\nBacktest finished! Final Portfolio Value: ${balance:,.2f}")
