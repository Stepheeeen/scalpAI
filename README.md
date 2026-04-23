# ScalpAI - XAUUSD High-Frequency Trading Bot

## 📈 Overview

ScalpAI is an advanced high-frequency trading bot specialized in XAUUSD (Gold vs USD) scalping. It uses machine learning (XGBoost) for signal generation, real-time market data from cTrader API, and comprehensive risk management. The bot features full Telegram integration for remote monitoring and account management.

**Key Capabilities:**
- Real-time XAUUSD trading with sub-millisecond execution
- AI-powered signal generation with 82%+ confidence threshold
- Automated risk management (stop-loss, take-profit, break-even)
- Multi-account support with live switching
- Complete Telegram control and monitoring
- Production-ready audit logging and performance tracking

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- cTrader demo/live account
- Telegram bot token
- Linux VPS (recommended for 24/7 operation)

### Installation

1. **Clone and Setup:**
   ```bash
   cd /root/scalpAI
   ./venv/bin/pip install -r requirements.txt
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your credentials
   ```

3. **Train AI Model:**
   ```bash
   ./venv/bin/python3 train_model.py
   ```

4. **Start Bot:**
   ```bash
   PYTHONPATH=/root/scalpAI/openapi_pb2 ./venv/bin/python3 main.py
   ```

---

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# cTrader API Credentials
CTRADER_CLIENT_ID=your_client_id_here
CTRADER_CLIENT_SECRET=your_client_secret_here
CTRADER_ACCESS_TOKEN=your_access_token_here
CTRADER_ACCOUNT_ID=46801669

# Telegram Bot
TELEGRAM_BOT_TOKEN=8313068465:AAGnzQQDYu6aa4wdVx7y0E394wQJPvDNLvE
TELEGRAM_CHAT_ID=your_chat_id_here
```

### Strategy Configuration (config.yaml)

```yaml
# cTrader Connection
ctrader:
  host: "demo.ctraderapi.com"  # Use "live.ctraderapi.com" for live trading
  port: 5035
  heartbeat_interval: 10
  watchdog_timeout: 30

# Trading Strategy
strategy:
  symbol_name: "XAUUSD"
  target_confidence: 0.82      # Minimum confidence for trade execution
  dry_run: false               # Set to true for testing without real trades
  model_path: "xgboost_gold_model.json"
  allow_mock_model: false      # Only use real AI model

# Risk Management
risk:
  max_drawdown_pct: 1.0        # Maximum account drawdown
  stop_loss_pips: 15           # Stop loss in pips
  take_profit_pips: 25         # Take profit in pips
  auto_break_even_pips: 5      # Auto break-even trigger

# Telegram Integration
telegram:
  enabled: true
  notifications:
    on_trade: true
    on_error: true
    on_reconnect: true

# Logging
logging:
  level: "INFO"
  log_to_file: true
  csv_file: "live_gold_data.csv"
  json_log: "bot_audit.log"
```

---

## 🤖 Telegram Control Center

ScalpAI features complete Telegram-based control and monitoring. All commands work only from your configured chat ID.

### Account Management Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message and overview | `/start` |
| `/help` | Show all available commands | `/help` |
| `/add_account <id> [desc]` | Add new trading account | `/add_account 46801669 "Demo Account"` |
| `/verify_account <id>` | Mark account as verified | `/verify_account 46801669` |
| `/remove_account <id>` | Remove account from list | `/remove_account 46801669` |
| `/list_accounts` | Show all accounts with status | `/list_accounts` |
| `/switch_account <id>` | **Live switch** to different account | `/switch_account 46801669` |
| `/account` | Show the current trading account details | `/account` |
| `/status` | Current bot status and info | `/status` |
| `/kpis` | Comprehensive key performance indicators | `/kpis` |
| `/performance` | Trading performance summary | `/performance` |
| `/pnl` | Profit & loss details | `/pnl` |
| `/stats` | Trading statistics and execution metrics | `/stats` |
| `/signals` | AI signal analysis and acceptance rates | `/signals` |
| `/stop` | Stop the bot and Telegram polling | `/stop` |
| `/reset_stats confirm` | Reset all performance statistics | `/reset_stats confirm` |

### Account Management Workflow

1. **Add Account:** `/add_account 46801669 "My Demo Account"`
2. **Test Connection:** Start bot and verify it connects
3. **Verify Account:** `/verify_account 46801669`
4. **Switch Live:** `/switch_account 46801669`

### Real-time Notifications

The bot automatically sends Telegram notifications for:
- ✅ **Bot Startup/Shutdown**
- 🚀 **Trade Executions** (entry/exit with PnL)
- ⚠️ **Errors & Reconnects**
- 📊 **Performance Summaries**
- 🔄 **Account Switches**
- 📈 **Signal Alerts** (in dry-run mode)

### KPI Monitoring Commands

Access comprehensive trading metrics anytime:
- **`/kpis`** - Complete performance dashboard
- **`/pnl`** - Profit/loss analysis
- **`/stats`** - Execution statistics
- **`/signals`** - AI signal performance
- **`/performance`** - Overall trading summary

---

## 🧠 Trading Logic

### Signal Generation Pipeline

1. **Data Ingestion:** Real-time XAUUSD tick data (bid/ask spreads)
2. **Feature Engineering:**
   - `spread`: Current bid-ask spread in pips
   - `velocity_100ms`: Price change over last 100ms
   - `velocity_500ms`: Price change over last 500ms
   - `velocity_1s`: Price change over last 1 second
   - `volatility`: Price variation standard deviation

3. **AI Prediction:** XGBoost model classifies signals:
   - `0`: No trade (hold)
   - `1`: Buy signal
   - `2`: Sell signal

4. **Confidence Filtering:** Only signals above 82% confidence proceed

5. **Position Management:** One position at a time with automatic break-even

### Risk Management

- **Stop Loss:** 15 pips automatic exit
- **Take Profit:** 25 pips profit target
- **Break-Even:** Automatic SL move to entry after 5 pips profit
- **Position Sizing:** Fixed volume (100 units)
- **Max Drawdown:** 1% account protection

### Execution Flow

```
Market Tick → Feature Extraction → AI Signal → Confidence Check → Risk Filter → Order Placement → Position Tracking → Auto Break-Even
```

---

## 📊 Monitoring & Analytics

### Real-time Dashboards

**Telegram Notifications:**
- Live trade executions with entry/exit prices
- Performance summaries after each trade
- Error alerts and reconnection status
- Signal confidence levels

**CSV Data Logging (`live_gold_data.csv`):**
- Timestamp, bid, ask prices
- Server latency measurements
- Feature values for analysis

**JSON Audit Log (`bot_audit.log`):**
- Structured event logging
- Trade performance metrics
- System health monitoring

### Performance Metrics

The bot tracks:
- **Win Rate:** Percentage of profitable trades
- **Average PnL:** Mean profit/loss per trade
- **Total PnL:** Cumulative account performance
- **Signal Accuracy:** AI prediction success rate
- **Execution Latency:** Order placement speed

### Health Monitoring

- **Connection Status:** WebSocket health and reconnection
- **API Response Times:** cTrader API latency
- **Memory Usage:** System resource monitoring
- **Error Rates:** Exception tracking and alerting

---

## 🔧 Operation Guide

### Starting the Bot

```bash
# Development mode
PYTHONPATH=/root/scalpAI/openapi_pb2 ./venv/bin/python3 main.py

# Production mode (with systemd)
sudo systemctl start scalpai-bot
```

### Daily Operation Checklist

1. **Pre-Market:**
   - Verify account balance and margin
   - Check Telegram connectivity: `/status`
   - Confirm AI model is loaded

2. **Market Hours:**
   - Monitor Telegram for trade alerts
   - Check performance: `/list_accounts` for PnL
   - Watch for error notifications

3. **Post-Market:**
   - Review daily performance summary
   - Backup logs and data files
   - Update AI model if needed

### Emergency Controls

- **Stop Trading:** Set `dry_run: true` in config.yaml
- **Account Switch:** `/switch_account <safe_account>`
- **Bot Shutdown:** Send SIGTERM or use systemd stop

---

## 🛡️ Safety & Risk Management

### Built-in Protections

- **Demo Mode:** `dry_run: true` for risk-free testing
- **Account Verification:** Only verified accounts can trade
- **Single Position:** Maximum one open position at a time
- **Stop Loss:** Mandatory loss protection on every trade
- **Drawdown Limits:** Automatic shutdown on excessive losses
- **Connection Monitoring:** Auto-reconnect on network issues

### Risk Parameters

```yaml
# Conservative Settings
risk:
  stop_loss_pips: 15      # 1.5 USD per lot
  take_profit_pips: 25    # 2.5 USD profit target
  auto_break_even_pips: 5 # Lock in profits early
  max_drawdown_pct: 1.0   # Stop at 1% loss
```

### Emergency Procedures

1. **High Loss Alert:** Bot automatically stops trading
2. **Connection Loss:** Automatic reconnection with backoff
3. **API Errors:** Telegram alerts with detailed error info
4. **Manual Override:** Use Telegram commands to switch accounts

---

## 📁 File Structure

```
scalpAI/
├── main.py                 # Main bot application
├── connection.py           # cTrader API client
├── brain.py               # AI signal generation
├── executioner.py         # Order management
├── performance.py         # Trade analytics
├── notifier.py            # Telegram integration
├── config_loader.py       # Configuration management
├── features.py            # Feature engineering
├── logger.py              # Data logging utilities
├── train_model.py         # AI model training
├── config.yaml            # Strategy configuration
├── .env                   # Environment variables
├── accounts.json          # Account management (auto-generated)
├── xgboost_gold_model.json # Trained AI model
├── live_gold_data.csv     # Tick data log
├── bot_audit.log          # Audit log
├── bot.service            # Systemd service file
├── setup_vps.sh           # VPS setup script
├── requirements.txt       # Python dependencies
└── README.md              # This manual
```

---

## 🚀 Deployment

### VPS Setup

1. **Server Requirements:**
   - Ubuntu 22.04+ or Debian 12+
   - 2GB RAM minimum, 4GB recommended
   - Low latency connection to cTrader servers

2. **Automated Setup:**
   ```bash
   chmod +x setup_vps.sh
   ./setup_vps.sh
   ```

3. **Systemd Service:**
   ```bash
   sudo cp bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable scalpai-bot
   sudo systemctl start scalpai-bot
   ```

### Production Checklist

- [ ] Environment variables configured securely
- [ ] Telegram bot token and chat ID verified
- [ ] AI model trained and tested
- [ ] Demo mode enabled for initial testing
- [ ] Systemd service configured
- [ ] Log rotation set up
- [ ] Backup strategy in place

---

## 🔍 Troubleshooting

### Common Issues

**Bot Won't Start:**
```bash
# Check Python path
PYTHONPATH=/root/scalpAI/openapi_pb2 python3 -c "import main"

# Verify protobuf modules
ls -la openapi_pb2/
```

**Telegram Not Working:**
- Verify bot token in `.env`
- Check chat ID is correct
- Test with `/start` command

**No Trading Signals:**
- Check if `xgboost_gold_model.json` exists
- Verify `allow_mock_model: false` in config
- Check confidence threshold (0.82)

**Connection Issues:**
- Verify cTrader credentials
- Check firewall settings
- Test with demo account first

### Log Analysis

```bash
# View recent activity
tail -f bot_audit.log

# Check for errors
grep ERROR bot_audit.log

# Performance summary
grep "Performance Summary" bot_audit.log
```

### Recovery Procedures

1. **Soft Restart:** `sudo systemctl restart scalpai-bot`
2. **Account Switch:** Use `/switch_account` via Telegram
3. **Emergency Stop:** Set `dry_run: true` and restart
4. **Full Reset:** Stop service, clear logs, restart

---

## 📈 Performance Optimization

### AI Model Training

```bash
# Generate more training data
./venv/bin/python3 generate_synthetic_data.py

# Retrain model
./venv/bin/python3 train_model.py

# Validate performance
grep "Training Complete" train_model.py
```

### Strategy Tuning

**Conservative Settings:**
```yaml
target_confidence: 0.85
stop_loss_pips: 20
take_profit_pips: 30
```

**Aggressive Settings:**
```yaml
target_confidence: 0.75
stop_loss_pips: 10
take_profit_pips: 20
```

### System Optimization

- Use SSD storage for logs
- Configure log rotation
- Monitor system resources
- Optimize Python garbage collection

---

## 📞 Support & Maintenance

### Regular Maintenance

- **Daily:** Check Telegram status updates
- **Weekly:** Review performance metrics
- **Monthly:** Retrain AI model with new data
- **Quarterly:** Update dependencies and security patches

### Getting Help

1. **Check Logs:** `tail -f bot_audit.log`
2. **Telegram Status:** `/status` command
3. **Performance Review:** Check CSV data files
4. **Configuration:** Verify `config.yaml` and `.env`

### Backup Strategy

```bash
# Daily backup
tar -czf backup_$(date +%Y%m%d).tar.gz \
    config.yaml .env accounts.json \
    xgboost_gold_model.json \
    live_gold_data.csv bot_audit.log
```

---

## ⚖️ Legal & Compliance

**Important Disclaimers:**
- This software is for educational and research purposes
- Trading involves substantial risk of loss
- Always test with demo accounts first
- Consult financial advisors before live trading
- Use at your own risk

**Demo vs Live Trading:**
- Demo accounts: Risk-free testing
- Live accounts: Real money at risk
- Start small and scale gradually
- Never risk more than you can afford to lose

---

## 🎯 Best Practices

### Risk Management
- Start with small position sizes
- Use demo accounts for testing
- Set conservative stop losses
- Monitor drawdown limits
- Have emergency stop procedures

### Performance Monitoring
- Track win rate and average PnL
- Review losing trades for patterns
- Update AI model regularly
- Monitor system performance

### Operational Excellence
- Use systemd for reliable operation
- Set up monitoring alerts
- Maintain comprehensive logs
- Have backup systems ready

---

*ScalpAI v1.0 - Advanced XAUUSD Trading Automation*
*Built with Python, XGBoost, and cTrader API*

### Examples
```
/add_account 46801669 "Demo Account"
/verify_account 46801669
/switch_account 46801669
/list_accounts
```

## Configuration

### config.yaml
```yaml
ctrader:
  host: "demo.ctraderapi.com"
  port: 5035

strategy:
  symbol_name: "XAUUSD"
  target_confidence: 0.82
  dry_run: false
  model_path: "xgboost_gold_model.json"
  allow_mock_model: false

risk:
  stop_loss_pips: 15
  take_profit_pips: 25
  auto_break_even_pips: 5

telegram:
  enabled: true

logging:
  level: "INFO"
  csv_file: "live_gold_data.csv"
  json_log: "bot_audit.log"
```

### Environment Variables (.env)
```
CTRADER_CLIENT_ID=your_client_id
CTRADER_CLIENT_SECRET=your_client_secret
CTRADER_ACCESS_TOKEN=your_access_token
CTRADER_ACCOUNT_ID=your_account_id
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Account Management

The bot supports multiple trading accounts with verification:

1. **Add Account**: Use `/add_account <id>` to register a new account
2. **Verify Account**: After testing connectivity, use `/verify_account <id>` to mark as verified
3. **Switch Account**: Use `/switch_account <id>` to change the active trading account
4. **List Accounts**: View all accounts with their verification status

Accounts are stored in `accounts.json` and persist across bot restarts.

## Trading Logic

1. **Data Collection**: Real-time XAUUSD tick data
2. **Feature Engineering**: Spread, velocity, volatility calculations
3. **Signal Generation**: XGBoost model predicts buy/sell/hold
4. **Risk Filtering**: Only execute signals above confidence threshold
5. **Order Execution**: Market orders with SL/TP
6. **Position Management**: Automatic break-even adjustments

## Safety Features

- **Demo Mode**: Set `dry_run: true` for testing without real trades
- **Risk Limits**: Configurable stop-loss and take-profit levels
- **Connection Monitoring**: Automatic reconnection on network issues
- **Position Limits**: Only one position at a time
- **Audit Logging**: Complete trade history and performance metrics

## Files

- `main.py` - Main bot application
- `connection.py` - cTrader API client
- `brain.py` - AI signal generation
- `executioner.py` - Order management and position tracking
- `performance.py` - Trade statistics and reporting
- `notifier.py` - Telegram integration and account management
- `config_loader.py` - Configuration management
- `train_model.py` - Model training script
- `accounts.json` - Stored account configurations

## Monitoring

All bot activity is logged to:
- **Telegram**: Real-time alerts and commands
- **CSV**: Tick data (`live_gold_data.csv`)
- **JSON**: Audit log (`bot_audit.log`)

## Deployment

For production deployment:

1. Set up systemd service (see `bot.service`)
2. Configure environment variables securely
3. Enable live trading mode in config
4. Monitor via Telegram commands

## Support

Use `/help` in Telegram for command reference, or check the audit logs for detailed bot activity.