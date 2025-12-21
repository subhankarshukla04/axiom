# Daily Price Update Schedule

## How It Works

Your portfolio prices now update **ONCE PER DAY** at market close, matching how institutional investors track portfolio performance.

### Update Schedule

- **Time**: 4:05 PM Eastern Time (ET) daily
- **Why 4:05 PM**: US stock market closes at 4:00 PM ET, we wait 5 minutes for final prices to settle
- **Frequency**: Once per day, Monday-Friday (market days)
- **Price Used**: Closing price of the day

### What Gets Updated

✅ **ALL companies with tickers automatically**
- When you add a new company (e.g., Tesla with ticker "TSLA"), it's automatically included
- No manual configuration needed
- Prices update for ALL stocks in your portfolio every day

### Technical Details

**Frontend (JavaScript)**:
- Checks every hour if it's time to update (4:05 PM ET or later)
- Uses `localStorage` to track last update date
- Only updates once per day even if you refresh the page multiple times
- Shows console message: "Next update: Tomorrow at 4:05 PM ET"

**Backend (Python)**:
- Fetches closing prices from Yahoo Finance
- Updates both `company_financials` and `valuation_results` tables
- No delays between requests (not needed for daily updates)
- Uses `period='1d'` to get the closing price

**API Calls**:
- **Before**: ~60 calls/hour (every 10 minutes)
- **Now**: ~7 calls/day (once daily at market close)
- **Reduction**: 99.5% fewer API calls!

### Benefits

1. **No Rate Limiting**: 7 API calls per day vs Yahoo's ~2000/hour limit
2. **Accurate Closing Prices**: Uses official market close prices
3. **Professional Standard**: Matches how institutional portfolios are valued
4. **Better Performance**: App loads faster, no constant background requests
5. **Consistent Valuation**: All stocks valued at same point in time each day

### Testing the Schedule

**Check if prices will update today**:
```javascript
// Open browser console (F12) and run:
const now = new Date();
const etTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
console.log(`Current ET time: ${etTime.toLocaleTimeString()}`);
console.log(`Hour: ${etTime.getHours()} (updates at hour >= 16)`);
```

**Manually trigger update** (for testing):
```javascript
// In browser console:
updatePortfolioPrices();
```

**Check last update time**:
```javascript
// In browser console:
const lastUpdate = localStorage.getItem('lastPriceUpdate');
console.log(`Last updated: ${new Date(lastUpdate).toLocaleString()}`);
```

### Adding New Companies

When you add a new company:

1. **Immediate**: Company appears in portfolio with import price
2. **Next Day 4:05 PM ET**: First automatic price update
3. **Every Day After**: Daily price updates at market close

**Example**:
- You add Microsoft (MSFT) at 2:00 PM today
- Import price: $420.50 (from Yahoo at time of import)
- Tomorrow at 4:05 PM ET: Updates to closing price (e.g., $422.15)
- Continues updating every day at 4:05 PM ET

### Market Holidays

On US market holidays (Christmas, Thanksgiving, etc.):
- Update attempts will run but may get stale prices
- Yahoo Finance returns last trading day's closing price
- No errors, just no new price movement

### Weekend Behavior

On Saturday/Sunday:
- No market, so no new prices
- Update will run but gets Friday's closing price
- Monday 4:05 PM ET gets Monday's closing price

### Console Messages

When you load the app, you'll see:
```
⏰ Starting daily price updates (once per day at market close)...
✅ Daily price update scheduler started
⏰ Next price update: Today at 4:05 PM ET (after market close)
```

After successful update:
```
📊 Market closed - updating prices at 4:05:00 PM ET
🔄 Fetching real-time prices...
💰 Updating 7 stock prices...
✅ Successfully updated 7/7 prices at 4:05:23 PM
⏰ Next update: Tomorrow at 4:05 PM ET (after market close)
```

### Rate Limiting Impact

**With 10 companies in portfolio**:

**OLD (10-minute updates)**:
- 6 updates/hour × 24 hours = 144 updates/day
- 144 updates × 10 companies = 1,440 API calls/day
- Risk: High chance of rate limiting

**NEW (daily closing price)**:
- 1 update/day × 10 companies = 10 API calls/day
- Risk: Zero chance of rate limiting
- Reduction: 99.3% fewer API calls

### Future Enhancements (Optional)

If you want more frequent updates in the future:
1. Add "Update Now" button for manual refresh
2. Enable real-time during market hours (9:30 AM - 4:00 PM ET only)
3. Cache prices for 15 minutes during market hours

For now, daily closing prices are the most reliable and professional approach.

---

## Summary

✅ Prices update once per day at 4:05 PM ET
✅ Uses closing prices (most accurate)
✅ Works for ALL companies automatically
✅ No rate limiting issues
✅ Professional institutional standard
✅ 99.5% reduction in API calls

Your portfolio now reflects end-of-day values, just like how professional fund managers track their positions.
