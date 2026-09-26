# Alpaca SPY Wheel Bot

An automated Python bot that executes a Wheel Options Strategy on `SPY` using the [Alpaca Trading API](https://alpaca.markets). It runs continuously, opening positions, monitoring for profit targets, defending in-the-money (ITM) options, and managing assignments, while sending execution alerts directly to Telegram.

## Strategy Rules
1. **Cash Secured Puts**: Sells 7 Days to Expiration (DTE), 2% Out-of-The-Money (OTM) puts if no SPY shares are held.
2. **Profit Taking**: Automatically buys to close the option and rolls it to a new 7 DTE contract when the current option reaches 75% profit.
3. **ITM Defense (Put Side)**: If the put option goes ITM, attempts to roll down and out to 7 DTE for a net credit of at least $10.00 in premium. If the credit target cannot be met, accepts assignment.
4. **Covered Calls**: If assigned (holds 100 shares of SPY), sells a 7 DTE call. The strike will be the higher of: 2% OTM or the original assignment strike.
5. **ITM Defense (Call Side)**: Similar to the put side, but attempts to roll *up* and out. If unavailable for a credit, accepts assignment (shares are called away) and switches back to selling puts.

## Prerequisites
- Python 3.9+
- An [Alpaca account](https://app.alpaca.markets) (Paper Trading enabled by default)
- A Telegram Bot Token (created via [@BotFather](https://t.me/BotFather)) and a Chat ID.

## Setup

1. **Clone the repository and set up your virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate
```

2. **Install the dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure your Environment Variables:**
Open the `.env` file and insert your API keys and Telegram credentials:
```env
ALPACA_API_KEY="your_api_key_here"
ALPACA_SECRET_KEY="your_secret_key_here"
ALPACA_PAPER_TRADE="true"
TELEGRAM_BOT_TOKEN="your_telegram_bot_token_here"
TELEGRAM_CHAT_ID="your_telegram_chat_id_here"
```

## Running the Bot

To start the bot, run the launcher from anywhere:

```bash
./run.sh
```

`run.sh` changes to the repository root and runs `wheel_spy.py` with the `venv/` Python, so the virtual environment must exist at `venv/` (see Setup). You can also run `python wheel_spy.py` from the repository root with the venv activated.

The bot runs indefinitely, checking the market clock every 6 minutes and evaluating positions whenever the market is open. Keep it running on a server or a machine that stays on during market hours.

## Run on startup

On Linux, `deploy/wheel-spy.service` is a systemd *user* unit that runs `run.sh`, restarts it 30 seconds after it exits, and logs to the journal.

> **Warning:** two running instances can double-sell options. Stop any manually started bot first (`pgrep -af wheel_spy`).

Install and enable it:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/wheel-spy.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable wheel-spy     # start on next boot
systemctl --user start wheel-spy      # start now (only if no manual instance)
loginctl enable-linger "$USER"        # start at boot without logging in
```

Manage it:

```bash
systemctl --user status wheel-spy
systemctl --user stop wheel-spy
systemctl --user disable wheel-spy    # don't start on boot
journalctl --user -u wheel-spy -f     # follow logs
```

The unit contains absolute paths to this repository; if you move the repo, update `WorkingDirectory` and `ExecStart` in the copied unit and run `systemctl --user daemon-reload`. The service does not wait for the network at boot. A bot that starts offline does not exit: each check that fails is logged and retried 6 minutes later; `Restart=always` only covers a crash.
